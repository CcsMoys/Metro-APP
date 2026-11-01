"""tunnel_mode.py — Telemetría sintética de Modo Túnel (Fase 6, Paso 6.2).

Cuando el dispositivo pierde señal (túnel subterráneo), el backend (o el propio
frontend en modo 100% offline) genera tramas de posición cada `interval` segundos
usando el motor de interpolación con jitter de velocidad realista:

- El tren avanza según el schedule GTFS pero con una velocidad multiplicada por
  un factor browniano (random walk acotado 0.85..1.15) => sin saltos.
- Se expone una sesión persistente: start()/tick()/stop().
- tick() devuelve la trama estilo GTFS-RT simplificada: lat/lon/bearing/speed/
  next_stop/eta_seconds, lista para consumir el frontend 3D.
"""
from __future__ import annotations

import math
import random
import time
import uuid
from dataclasses import dataclass, field

import pandas as pd


@dataclass
class TunnelSession:
    session_id: str
    trip_id: str
    t_virtual: pd.Timedelta          # "reloj" del tren dentro del día
    speed_factor: float = 1.0
    started_at: float = field(default_factory=time.time)
    last_tick: float = field(default_factory=time.time)
    dead: bool = False

    def to_dict(self):
        return {"session_id": self.session_id, "trip_id": self.trip_id,
                "t_virtual": str(self.t_virtual), "speed_factor": round(self.speed_factor, 3)}


class TunnelEngine:
    """Generador de tramas sintéticas sobre el PositionEngine existente."""

    def __init__(self, position_engine, interval_s: float = 2.0):
        self.engine = position_engine
        self.interval_s = interval_s
        self.sessions: dict[str, TunnelSession] = {}
        self.rng = random.Random(42)

    # --------------------------- API de sesiones ---------------------------- #
    def start(self, trip_id: str | None = None, t: str | None = None) -> dict:
        segs = self.engine.segments
        if segs.empty:
            raise RuntimeError("no hay segmentos GTFS cargados")
        if trip_id is None:
            trip_id = str(segs.iloc[0]["trip_id"])
        td = _parse_t(t) if t else _now_timedelta()
        # encontrar el segmento activo más reciente para ese trip (o el primero)
        cand = segs[segs["trip_id"] == trip_id].sort_values("t0")
        if cand.empty:
            raise KeyError(f"trip {trip_id} no existe")
        row = cand[cand["t0"] <= td].iloc[-1] if (cand["t0"] <= td).any() else cand.iloc[0]
        s = TunnelSession(session_id=uuid.uuid4().hex[:12], trip_id=trip_id,
                          t_virtual=row["t0"])
        self.sessions[s.session_id] = s
        return {"ok": True, **s.to_dict(), "frame": self._frame(s)}

    def tick(self, session_id: str) -> dict:
        s = self.sessions.get(session_id)
        if not s or s.dead:
            raise KeyError("sesión de túnel no encontrada o finalizada")
        now = time.time()
        dt = max(now - s.last_tick, 0.05)
        s.last_tick = now
        # paseo browniano del factor de velocidad (sin saltos bruscos)
        s.speed_factor = min(1.15, max(0.85, s.speed_factor + self.rng.uniform(-0.03, 0.03)))
        s.t_virtual = s.t_virtual + pd.Timedelta(seconds=dt * s.speed_factor)
        frame = self._frame(s)
        if frame is None:
            s.dead = True
            return {"ok": True, "finished": True, "session_id": session_id}
        return {"ok": True, "finished": False, "session_id": session_id, "frame": frame}

    def stop(self, session_id: str) -> dict:
        s = self.sessions.pop(session_id, None)
        return {"ok": s is not None}

    def active(self) -> list[dict]:
        return [s.to_dict() for s in self.sessions.values() if not s.dead]

    # ------------------------------ internals ------------------------------- #
    def _frame(self, s: TunnelSession) -> dict | None:
        segs = self.engine.segments
        cur = segs[(segs["trip_id"] == s.trip_id) &
                   (segs["t0"] <= s.t_virtual) & (segs["t1"] > s.t_virtual)]
        if cur.empty:
            # buscar si ya terminó el viaje
            remaining = segs[(segs["trip_id"] == s.trip_id) & (segs["t0"] > s.t_virtual)]
            if remaining.empty:
                return None
            # en espera entre tramos: reportar última parada como posición
            last = segs[(segs["trip_id"] == s.trip_id) & (segs["t1"] <= s.t_virtual)].iloc[-1]
            pos = _point_on_segment(self.engine.shapes, last, 1.0)
            nxt = remaining.iloc[0]
            eta = float((nxt["t0"] - s.t_virtual).total_seconds())
            return {**pos, "trip_id": s.trip_id, "route_id": last["route_id"],
                    "speed_kmh": 0.0, "state": "en_estacion",
                    "next_stop": nxt["next_stop"],
                    "next_stop_eta_s": round(max(0.0, eta), 1), "synthetic": True}
        row = cur.iloc[0]
        span = (row["t1"] - row["t0"]).total_seconds()
        frac = (s.t_virtual - row["t0"]).total_seconds() / span if span > 0 else 1.0
        pos = _point_on_segment(self.engine.shapes, row, min(frac, 1.0))
        eta = float((row["t1"] - s.t_virtual).total_seconds())
        return {**pos, "trip_id": s.trip_id, "route_id": row["route_id"],
                "speed_kmh": round(_approx_speed(row, frac, s.speed_factor), 1),
                "state": "en_tunel" if _in_tunnel(pos) else "en_via",
                "next_stop": row["next_stop"],
                "next_stop_eta_s": round(eta, 1), "synthetic": True}


def _point_on_segment(shapes: dict, row, frac: float) -> dict:
    """Interpola lat/lon/bearing sobre el shape del segmento, fracción 0..1."""
    line = shapes.get(row["shape_id"])
    d = float(row["d0"]) + frac * (float(row["d1"]) - float(row["d0"]))
    if line is None:
        return {"lat": 0.0, "lon": 0.0, "bearing": 0.0}
    d = min(max(d, 0.0), line.length)
    p = line.interpolate(d)
    ahead = line.interpolate(min(d + max(0.0002, 0.01 * line.length), line.length))
    brg = _bearing_deg((p.x, p.y), (ahead.x, ahead.y))
    return {"lat": round(p.y, 6), "lon": round(p.x, 6), "bearing": round(brg, 1)}


def _bearing_deg(p0, p1):
    import math
    lon1, lat1 = p0
    lon2, lat2 = p1
    d_lon = math.radians(lon2 - lon1)
    y = math.sin(d_lon) * math.cos(math.radians(lat2))
    x = (math.cos(math.radians(lat1)) * math.sin(math.radians(lat2))
         - math.sin(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.cos(d_lon))
    return (math.degrees(math.atan2(y, x)) + 360) % 360


def _in_tunnel(pos: dict) -> bool:
    """Heurística demo: estaciones subterráneas marcadas en el engine."""
    return True  # Línea 1/2/3/4 mayormente subterránea en el MVP


def _approx_speed(row, frac: float, factor: float) -> float:
    """Velocidad aproximada km/h a partir de d0/d1 (grados) y tiempos."""
    try:
        dm = (row["d1"] - row["d0"])
        # d está en unidades del shape (grados ~ 111 km por grado lat)
        dist_km = abs(dm) * 111.0
        span_h = max((row["t1"] - row["t0"]).total_seconds(), 1) / 3600.0
        return (dist_km / span_h) * factor
    except Exception:
        return 35.0


def _parse_t(t: str) -> pd.Timedelta:
    h, m, sec = (int(x) for x in t.split(":"))
    return pd.Timedelta(hours=h, minutes=m, seconds=sec)


def _now_timedelta() -> pd.Timedelta:
    now = time.localtime()
    return pd.Timedelta(hours=now.tm_hour, minutes=now.tm_min, seconds=now.tm_sec)
