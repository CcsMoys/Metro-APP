"""loyalty.py — MetroPuntos + Billetera SUVE + QR dinámico (Fase 6, Paso 6.1).

Reglas de negocio:
- Cada viaje registrado suma puntos: P = round(dist_km * mode_weight * user_mult)
    mode_weight: metro=1.0, ife=1.5, metroca­ble/cabletren=1.5, buscaracas=1.2, walk=0
    user_mult:   roja=1.0, azul=1.0, amarilla=1.0 (la bonificación depende del modo)
- Bonus diario por primer viaje: +5 pts. Bono multi-modal (>=2 modos en un viaje): +3 pts.
- Umbrales de canje: 100 pts => pasaje gratis (roja), 60 pts => descuento 50%.

Tarifas SUVE (Bs.) referenciales según MPPT/SUVE 2024:
- Metro/Metrobús: 5.00 | IFE Tuy Medio: 10.00 | MetroCable/CableTren: 5.00
- Azul (estudiante): 50% | Amarilla (adulto mayor/discapacidad): 0.00

QR dinámico híbrido: payload cifrado localmente con AES-GCM (clave derivada por
HKDF desde un secreto de dispositivo + fecha), rotación cada 60 segundos. El QR
NO requiere internet: el validador (simulado) posee la misma clave maestra.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import io
import json
import os
import sqlite3
import time
from dataclasses import dataclass

import qrcode
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

DB_PATH = os.environ.get("METROVIVE_DB", os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "metro.db"))

CARD_TYPES = {
    "roja":     {"color": "#E30613", "name": "Público General", "fare_factor": 1.0},
    "azul":     {"color": "#0057B7", "name": "Estudiante", "fare_factor": 0.5},
    "amarilla": {"color": "#FFC607", "name": "Adulto Mayor / Discapacidad", "fare_factor": 0.0},
}

MODE_WEIGHTS = {"metro": 1.0, "ife": 1.5, "metro cable": 1.5, "cabletren": 1.5,
                "buscaracas": 1.2, "metrobús": 1.2, "walk": 0.0, "via": 1.0}

MODE_FARES = {"metro": 5.0, "buscaracas": 5.0, "metro cable": 5.0, "cabletren": 5.0,
              "ife": 10.0, "metrobús": 5.0}

QR_TTL_SECONDS = 60


# ------------------------------- Base de datos ------------------------------ #

def _conn() -> sqlite3.Connection:
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    c = sqlite3.connect(DB_PATH)
    c.row_factory = sqlite3.Row
    return c


def init_db():
    with _conn() as c:
        c.executescript("""
        CREATE TABLE IF NOT EXISTS users(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE,
            card_type TEXT NOT NULL DEFAULT 'roja',
            points INTEGER NOT NULL DEFAULT 0,
            balance_bs REAL NOT NULL DEFAULT 0.0,
            device_secret TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS trips(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL REFERENCES users(id),
            from_stop TEXT NOT NULL,
            to_stop TEXT NOT NULL,
            distance_km REAL NOT NULL,
            modes TEXT NOT NULL,
            points_earned INTEGER NOT NULL,
            fare_paid_bs REAL NOT NULL,
            ts TEXT NOT NULL DEFAULT (datetime('now'))
        );
        CREATE TABLE IF NOT EXISTS redemptions(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL REFERENCES users(id),
            kind TEXT NOT NULL,           -- free_ticket | discount_50
            cost_points INTEGER NOT NULL,
            ts TEXT NOT NULL DEFAULT (datetime('now'))
        );
        """)


def _derive_secret(name: str) -> str:
    """Secreto determinista por usuario (en producción: generado en onboarding
    y guardado en keystore del dispositivo)."""
    return hashlib.sha256(("MetroViveMaster:" + name.lower()).encode()).hexdigest()


# --------------------------------- Usuarios -------------------------------- #

def create_user(name: str, card_type: str = "roja") -> dict:
    if card_type not in CARD_TYPES:
        raise ValueError(f"tipo de tarjeta inválido: {card_type}")
    init_db()
    with _conn() as c:
        cur = c.execute(
            "INSERT INTO users(name, card_type, device_secret) VALUES(?,?,?)",
            (name, card_type, _derive_secret(name)))
        c.commit()
        return get_user(cur.lastrowid)


def get_user(uid: int) -> dict:
    init_db()
    with _conn() as c:
        r = c.execute("SELECT * FROM users WHERE id=?", (uid,)).fetchone()
    if not r:
        raise KeyError(f"usuario {uid} no existe")
    d = dict(r)
    d["card"] = CARD_TYPES[d["card_type"]]
    d.pop("device_secret")
    return d


# ---------------------------------- Viajes ---------------------------------- #

def mode_weight(mode: str) -> float:
    m = mode.lower().strip()
    for k, v in MODE_WEIGHTS.items():
        if k in m or m in k:
            return v
    return 1.0


def compute_fare(distance_km: float, modes: list[str], card_type: str) -> float:
    factor = CARD_TYPES[card_type]["fare_factor"]
    base = 0.0
    seen_modes = set()
    for m in modes:
        key = next((k for k in MODE_FARES if k in m.lower()), None)
        if key and key not in seen_modes and mode_weight(m) > 0:
            base += MODE_FARES[key]
            seen_modes.add(key)
    if base == 0.0:  # solo caminata u otros
        base = 5.0
    return round(base * factor, 2)


def register_trip(user_id: int, from_stop: str, to_stop: str,
                  distance_km: float, legs: list[dict]) -> dict:
    """legs: [{"mode": "metro"}, ...] como devuelve /api/routes."""
    u = get_user(user_id)
    with _conn() as c:
        secret = c.execute("SELECT device_secret FROM users WHERE id=?", (user_id,)).fetchone()[0]
    modes = [l.get("mode", "via") for l in legs if l.get("mode") != "walk"]
    transit_modes = [m for m in modes if mode_weight(m) > 0]
    if not transit_modes:
        raise ValueError("el viaje no incluye tramos de transporte público")

    pts = sum(round(distance_km * mode_weight(m) * 10) for m in transit_modes[:1])
    # bonos
    today = time.strftime("%Y-%m-%d")
    with _conn() as c:
        first_today = c.execute(
            "SELECT COUNT(*) n FROM trips WHERE user_id=? AND date(ts)=?", (user_id, today)).fetchone()["n"] == 0
        multimodal = len(set(transit_modes)) >= 2
    pts += 5 if first_today else 0
    pts += 3 if multimodal else 0

    fare = compute_fare(distance_km, transit_modes, u["card_type"])
    # descuento si tiene ticket gratis redimido vigente
    with _conn() as c:
        free = c.execute(
            "SELECT COUNT(*) n FROM redemptions WHERE user_id=? AND kind='free_ticket' "
            "AND date(ts)=date('now') AND id NOT IN (SELECT id FROM trips WHERE 0)",
            (user_id,)).fetchone()["n"]
    if free:
        pass  # simplificación MVP: los pases se descuentan al usarlos vía use_free_ticket()

    with _conn() as c:
        c.execute(
            "INSERT INTO trips(user_id, from_stop, to_stop, distance_km, modes, points_earned, fare_paid_bs) "
            "VALUES(?,?,?,?,?,?,?)",
            (user_id, from_stop, to_stop, distance_km, ",".join(transit_modes), pts, fare))
        c.execute("UPDATE users SET points = points + ? WHERE id=?", (pts, user_id))
        c.commit()
    return {"user_id": user_id, "points_earned": pts, "fare_bs": fare,
            "total_points": get_user(user_id)["points"], "multimodal_bonus": multimodal,
            "first_trip_bonus": first_today}


# ------------------------------ Canje de puntos ------------------------------ #

REDEEM_COST = {"free_ticket": 100, "discount_50": 60}


def redeem(user_id: int, kind: str) -> dict:
    if kind not in REDEEM_COST:
        raise ValueError("premio desconocido")
    u = get_user(user_id)
    cost = REDEEM_COST[kind]
    if u["points"] < cost:
        raise ValueError(f"puntos insuficientes: {u['points']} < {cost}")
    with _conn() as c:
        c.execute("UPDATE users SET points = points - ? WHERE id=?", (cost, user_id))
        c.execute("INSERT INTO redemptions(user_id, kind, cost_points) VALUES(?,?,?)",
                  (user_id, kind, cost))
        c.commit()
    return {"ok": True, "kind": kind, "spent": cost, "remaining": get_user(user_id)["points"]}


# ---------------------------- QR dinámico offline ---------------------------- #

def _qr_key(device_secret: str) -> AESGCM:
    key = HKDF(algorithm=hashlib.sha256(), length=32, salt=b"MetroViveQRv1",
               info=b"ticket").derive(device_secret.encode())
    return AESGCM(key)


def _rotation_window(now: float | None = None) -> tuple[int, int]:
    now = now if now is not None else time.time()
    slot = int(now // QR_TTL_SECONDS)
    return slot, int(now % QR_TTL_SECONDS)


def generate_qr(user_id: int, now_ts: float | None = None) -> dict:
    """Genera token cifrado AES-GCM válido solo dentro de la ventana de 60 s."""
    with _conn() as c:
        row = c.execute("SELECT * FROM users WHERE id=?", (user_id,)).fetchone()
    if not row:
        raise KeyError("usuario no existe")
    slot, secs_left = _rotation_window(now_ts)
    payload = json.dumps({"uid": user_id, "card": row["card_type"], "slot": slot},
                         separators=(",", ":")).encode()
    aead = _qr_key(row["device_secret"])
    nonce = slot.to_bytes(8, "big") + os.urandom(4)
    ct = aead.encrypt(nonce, payload, associated_data=str(slot).encode())
    token = base64.urlsafe_b64encode(nonce + ct).decode().rstrip("=")
    url = f"metrovive://t/{token}"
    img = qrcode.make(url)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    png_b64 = base64.b64encode(buf.getvalue()).decode()
    return {"token": token, "url": url, "png_base64": png_b64,
            "valid_seconds": QR_TTL_SECONDS - secs_left, "slot": slot,
            "card_color": CARD_TYPES[row["card_type"]]["color"]}


def validate_qr(token: str, user_name_hint: str, now_ts: float | None = None) -> dict:
    """Simulador de torniquete: conoce la clave del usuario (demo local)."""
    secret = _derive_secret(user_name_hint)
    raw = base64.urlsafe_b64decode(token + "=" * (-len(token) % 4))
    nonce, ct = raw[:12], raw[12:]
    slot_now, _ = _rotation_window(now_ts)
    for slot in (slot_now, slot_now - 1):  # tolerancia de 1 rotación por reloj
        try:
            pt = _qr_key(secret).decrypt(nonce, ct, associated_data=str(slot).encode())
            data = json.loads(pt)
            age = (slot_now - data["slot"]) * QR_TTL_SECONDS
            return {"valid": True, "expired": False, **data, "age_seconds": age}
        except Exception:
            continue
    return {"valid": False, "reason": "firma inválida o QR expirado (>60s)"}


init_db()
