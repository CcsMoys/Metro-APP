"""position_engine.py — Motor de interpolación cinemática (Fase 2, Paso 2.2).

Para un instante t:
1. Busca los segmentos stop_times activos (tren entre salida de parada k y llegada k+1).
2. Calcula la fracción de avance y la distancia sobre el shape.
3. Interpola la posición con Shapely LineString.interpolate(dist) -> lat/lon + bearing.

Los segmentos se precalculan una sola vez (distancias acumuladas d0/d1 por parada
sobre su shape), de modo que positions_at() es solo búsqueda vectorizada + interpolate.
"""
from __future__ import annotations

import math

import pandas as pd
from shapely.geometry import LineString, Point

from .gtfs_loader import GtfsBundle, load_gtfs


def _bearing_deg(p0, p1):
    """Rumbo geodésico aproximado (norte=0, sentido horario) en grados."""
    lon1, lat1 = p0
    lon2, lat2 = p1
    d_lon = math.radians(lon2 - lon1)
    y = math.sin(d_lon) * math.cos(math.radians(lat2))
    x = (math.cos(math.radians(lat1)) * math.sin(math.radians(lat2))
         - math.sin(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.cos(d_lon))
    return (math.degrees(math.atan2(y, x)) + 360) % 360


def build_shapes(bundle: GtfsBundle) -> dict[str, LineString]:
    shapes: dict[str, LineString] = {}
    if bundle.shapes.empty:
        return shapes
    for shape_id, g in bundle.shapes.sort_values("shape_pt_sequence").groupby("shape_id"):
        coords = list(zip(g["shape_pt_lon"], g["shape_pt_lat"]))
        if len(coords) >= 2:
            shapes[shape_id] = LineString(coords)
    return shapes


def build_segments(bundle: GtfsBundle, shapes: dict[str, LineString]) -> pd.DataFrame:
    """Precalcula (trip, tramo) con t0,t1,d0,d1,shape_id,next_stop."""
    st = bundle.stop_times
    if st.empty:
        return pd.DataFrame()
    trips = bundle.trips.set_index("trip_id")
    stops = bundle.stops.set_index("stop_id")

    rows = []
    for trip_id, g in st.sort_values(["trip_id", "stop_sequence"]).groupby("trip_id"):
        try:
            shape_id = trips.loc[trip_id, "shape_id"]
            route_id = trips.loc[trip_id, "route_id"]
        except KeyError:
            continue
        line = shapes.get(shape_id)
        g = g.reset_index(drop=True)
        # distancia acumulada de cada parada proyectada sobre el shape
        dists = []
        for sid in g["stop_id"]:
            if sid not in stops.index:
                dists.append(float("nan"))
                continue
            s = stops.loc[sid]
            pt = (float(s["stop_lon"]), float(s["stop_lat"]))
            if line is None:
                dists.append(float("nan"))
            else:
                dists.append(line.project(Point(pt)))
        for i in range(len(g) - 1):
            t0, t1 = g.at[i, "departure_time"], g.at[i + 1, "arrival_time"]
            if pd.isna(t1) or t1 <= t0:
                continue
            d0, d1 = dists[i], dists[i + 1]
            if pd.isna(d0) or pd.isna(d1):
                continue
            rows.append({
                "trip_id": trip_id, "route_id": route_id, "shape_id": shape_id,
                "t0": t0, "t1": t1, "d0": float(d0), "d1": float(d1),
                "prev_stop": g.at[i, "stop_id"], "next_stop": g.at[i + 1, "stop_id"],
            })
    seg = pd.DataFrame(rows)
    if not seg.empty:
        seg = seg.sort_values(["t0"]).reset_index(drop=True)
    return seg


def positions_at(t: pd.Timedelta, segments: pd.DataFrame,
                 shapes: dict[str, LineString]) -> list[dict]:
    """Estado de todos los trenes en el instante t (timedelta desde medianoche)."""
    if segments.empty:
        return []
    active = segments[(segments.t0 <= t) & (segments.t1 > t)].copy()
    if active.empty:
        return []
    frac = ((t - active.t0) / (active.t1 - active.t0)).to_numpy(dtype=float)
    dist = active.d0.to_numpy() + frac * (active.d1.to_numpy() - active.d0.to_numpy())

    out = []
    for (idx, row), d, f in zip(active.iterrows(), dist, frac):
        line = shapes.get(row.shape_id)
        if line is None:
            continue
        p = line.interpolate(min(max(d, 0), line.length))
        # bearing: punto ligeramente por delante
        ahead = line.interpolate(min(d + max(0.0002, 0.01 * line.length), line.length))
        brg = _bearing_deg((p.x, p.y), (ahead.x, ahead.y))
        out.append({
            "trip_id": row.trip_id, "route_id": row.route_id,
            "lat": round(p.y, 6), "lon": round(p.x, 6),
            "bearing": round(brg, 1), "next_stop": row.next_stop,
            "progress": round(float(f), 3),
        })
    return out


class PositionEngine:
    """Envuelve loader+segmentos; resuelve t a partir de hora local (America/Caracas)."""

    def __init__(self, gtfs_dir=None):
        self.bundle = load_gtfs(gtfs_dir) if gtfs_dir else load_gtfs()
        self.shapes = build_shapes(self.bundle)
        self.segments = build_segments(self.bundle, self.shapes)

    def at_time(self, hhmmss: str) -> list[dict]:
        h, m, s = map(int, hhmmss.split(":"))
        return positions_at(pd.Timedelta(hours=h, minutes=m, seconds=s),
                            self.segments, self.shapes)

    def now(self) -> list[dict]:
        import datetime
        now = datetime.datetime.now()
        return self.at_time(now.strftime("%H:%M:%S"))


if __name__ == "__main__":
    eng = PositionEngine()
    trains = eng.at_time("08:00:00")
    print(f"[OK] segmentos precalculados: {len(eng.segments)} | trenes activos 08:00 = {len(trains)}")
    assert len(trains) > 0
    l1 = [x for x in trains if x["route_id"] == "metro:L1"]
    assert l1, "debe haber trenes L1 a las 08:00"
    # prueba: coordenadas caen sobre el shape L1 (distancia ~0 al proyectar)
    from shapely.geometry import Point
    line = eng.shapes["metro:L1"]
    worst = max(line.distance(Point(x["lon"], x["lat"])) for x in l1)
    print(f"[OK] desviación máxima vs. vía L1: {worst:.8f}° (~{worst*111000:.1f} m)")
    assert worst < 1e-4
    print("ejemplo:", l1[0])
