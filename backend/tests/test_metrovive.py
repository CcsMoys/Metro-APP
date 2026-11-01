"""Pruebas automatizadas MetroVive (Fases 1,2,5,6).
Ejecutar: cd backend && python -m pytest tests/ -v
Diseñado para correr en CI (GitHub Actions) sin Ollama ni red externa.
"""
import os
import sys
import time

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ["METROVIVE_DB"] = os.path.join(os.path.dirname(__file__), "test_metro.db")

if os.path.exists(os.environ["METROVIVE_DB"]):
    os.remove(os.environ["METROVIVE_DB"])

from app.main import app  # noqa: E402
from app import loyalty   # noqa: E402

client = TestClient(app)
client.__enter__()  # dispara el evento startup (carga GTFS, grafo, motores)


# ------------------------------- Fase 1-2 ---------------------------------- #

def test_health():
    r = client.get("/api/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert body["segments"] > 1000
    assert body["routes"] >= 7


def test_positions_0800():
    r = client.get("/api/trains/positions?t=08:00:00")
    assert r.status_code == 200
    trains = r.json()["trains"]
    assert len(trains) > 20
    l1 = [t for t in trains if t["route_id"] == "metro:L1"]
    assert l1, "debe haber trenes L1 a las 08:00"
    for t in l1[:5]:
        assert 10.3 < t["lat"] < 10.6 and -67.1 < t["lon"] < -66.7


def test_positions_bad_time():
    assert client.get("/api/trains/positions?t=25:99").status_code == 400


def test_route_multimodal():
    r = client.get("/api/routes?from=metro:propatria&to=metro:palo-verde")
    assert r.status_code == 200
    body = r.json()
    assert body["total_km"] > 10
    assert len(body["legs"]) >= 15


def test_route_capitolio_zona_rental_l4():
    """L4 directa Capitolio → Zona Rental (prueba del Plan B)."""
    r = client.get("/api/routes?from=metro:capitolio&to=metro:zona-rental")
    assert r.status_code == 200
    legs = r.json()["legs"]
    assert any("metro" in l["mode"] for l in legs)


# --------------------------------- Fase 5 ---------------------------------- #

@pytest.mark.parametrize("msg,must", [
    ("¿Cómo llego de Capitolio a Zona Rental?", ["Ruta"]),
    ("estado", ["trenes"]),
    ("ayuda", ["Puedo"]),
])
def test_chat_fallback(msg, must):
    r = client.post("/api/chat", json={"message": msg})
    assert r.status_code == 200
    body = r.json()
    assert any(w.lower() in body["reply"].lower() for w in must)
    assert body["engine"] == "rule-fallback" or body["engine"].startswith("ollama")


def test_chat_unknown_station():
    r = client.post("/api/chat", json={"message": "¿Cómo llego de Xyzabw a Qqq?"})
    assert r.status_code == 200
    assert "no reconozco" in r.json()["reply"].lower()


# --------------------------------- Fase 6 ---------------------------------- #

def test_user_and_cards():
    u = client.post("/api/users", json={"name": "Ana_test", "card_type": "azul"}).json()
    assert u["card"]["color"] == "#0057B7"
    bad = client.post("/api/users", json={"name": "X", "card_type": "verde"})
    assert bad.status_code == 400


def test_trip_points_and_fare():
    client.post("/api/users", json={"name": "Carlos_test", "card_type": "roja"})
    uid = loyalty._conn().execute("SELECT id FROM users WHERE name='Carlos_test'").fetchone()["id"]
    r = client.post("/api/trips", json={"user_id": uid,
                                         "from_stop": "metro:propatria",
                                         "to_stop": "metro:cua"})
    assert r.status_code == 200
    body = r.json()
    assert body["points_earned"] > 0
    assert body["fare_bs"] == 5.0  # tarifa metro roja


def test_redeem_flow():
    uid = loyalty.create_user("Pedro_rich", "roja")["id"]
    with loyalty._conn() as c:
        c.execute("UPDATE users SET points=150 WHERE id=?", (uid,))
    ok = client.post("/api/redeem", json={"user_id": uid, "kind": "free_ticket"})
    assert ok.status_code == 200
    assert ok.json()["remaining"] == 50
    fail = client.post("/api/redeem", json={"user_id": uid, "kind": "free_ticket"})
    assert fail.status_code == 400


def test_qr_rotation_and_expiry():
    uid = loyalty.create_user("Maria_qr", "amarilla")["id"]
    now = time.time()
    qr = loyalty.generate_qr(uid, now_ts=now)
    assert qr["png_base64"] and qr["valid_seconds"] <= 60
    v = loyalty.validate_qr(qr["token"], "Maria_qr", now_ts=now)
    assert v["valid"] is True
    # expirado tras varias ventanas (>60s) => rechazado
    v2 = loyalty.validate_qr(qr["token"], "Maria_qr", now_ts=now + 180)
    assert v2["valid"] is False
    # token válido pero usuario incorrecto => rechazado
    v3 = loyalty.validate_qr(qr["token"], "OtroUsuario", now_ts=now)
    assert v3["valid"] is False


def test_qr_endpoint():
    uid = loyalty.create_user("Sofia_api", "roja")["id"]
    r = client.get(f"/api/qr/{uid}")
    assert r.status_code == 200
    tok = r.json()["token"]
    v = client.post("/api/qr/validate", json={"token": tok, "user_name": "Sofia_api"})
    assert v.json()["valid"] is True


# ------------------------------ Modo Túnel --------------------------------- #

def test_tunnel_session_moves_without_jumps():
    r = client.post("/api/tunnel/start", json={"trip_id": None, "t": "08:00:00"})
    assert r.status_code == 200, r.text
    sid = r.json()["session_id"]
    f0 = r.json()["frame"]
    assert f0["synthetic"] is True
    prev_lat, prev_lon = f0["lat"], f0["lon"]
    moved = False
    for _ in range(3):
        time.sleep(0.06)
        t = client.post("/api/tunnel/tick", json={"session_id": sid}).json()
        if t.get("finished"):
            break
        fr = t["frame"]
        # sin saltos: desplazamiento entre ticks pequeño (< ~0.01° ≈ 1 km)
        assert abs(fr["lat"] - prev_lat) < 0.01
        assert abs(fr["lon"] - prev_lon) < 0.01
        if abs(fr["lat"] - prev_lat) + abs(fr["lon"] - prev_lon) > 0:
            moved = True
        prev_lat, prev_lon = fr["lat"], fr["lon"]
    assert moved, "el tren debe avanzar con tramas sintéticas"
    s = client.post("/api/tunnel/stop", json={"session_id": sid})
    assert s.json()["ok"] is True


def test_tunnel_bad_session():
    assert client.post("/api/tunnel/tick", json={"session_id": "nope"}).status_code == 404
