"""gtfs_loader.py — Carga y parseo del paquete GTFS estático (Fase 2, Paso 2.1).

Puntos críticos (Plan B):
- Los tiempos se parsean como timedelta desde medianoche, NUNCA como hora de reloj,
  porque GTFS permite viajes que cruzan la medianoche escritos como "24:20:00".
- Expone GtfsBundle con DataFrames listos para el motor de posiciones.
"""
from __future__ import annotations

import os
from dataclasses import dataclass

import pandas as pd

GTFS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                        "data", "gtfs")


def parse_gtfs_time(s: str) -> pd.Timedelta:
    """'HH:MM:SS' -> Timedelta. Soporta horas >= 24 (viajes post-medianoche)."""
    parts = str(s).strip().split(":")
    if len(parts) != 3:
        raise ValueError(f"Tiempo GTFS inválido: {s!r}")
    h, m, sec = int(parts[0]), int(parts[1]), int(parts[2])
    return pd.Timedelta(hours=h, minutes=m, seconds=sec)


@dataclass
class GtfsBundle:
    stops: pd.DataFrame
    routes: pd.DataFrame
    trips: pd.DataFrame
    stop_times: pd.DataFrame
    shapes: pd.DataFrame
    calendar: pd.DataFrame

    def is_active(self, date: pd.Timestamp | None = None) -> set[str]:
        """service_ids activos para una fecha (calendario simple diario)."""
        if self.calendar.empty:
            return set()
        c = self.calendar
        day = (date or pd.Timestamp.now()).strftime("%A").lower()[:3]
        mask = c[[day]].squeeze(axis=1).astype(str) == "1"
        return set(c.loc[mask, "service_id"])


def load_gtfs(gtfs_dir: str = GTFS_DIR) -> GtfsBundle:
    def read(name, **kw):
        p = os.path.join(gtfs_dir, f"{name}.txt")
        return pd.read_csv(p, dtype=str, **kw) if os.path.exists(p) else pd.DataFrame()

    stops = read("stops")
    routes = read("routes")
    trips = read("trips")
    stop_times = read("stop_times")
    shapes = read("shapes")
    calendar = read("calendar")

    for col in ("arrival_time", "departure_time"):
        if col in stop_times:
            stop_times[col] = stop_times[col].map(parse_gtfs_time)
    for df, cols in ((stops, ("stop_lat", "stop_lon")), (shapes, ("shape_pt_lat", "shape_pt_lon"))):
        for c in cols:
            if c in df:
                df[c] = df[c].astype(float)
    if "stop_sequence" in stop_times:
        stop_times["stop_sequence"] = stop_times["stop_sequence"].astype(int)
    return GtfsBundle(stops, routes, trips, stop_times, shapes, calendar)


if __name__ == "__main__":
    b = load_gtfs()
    print(f"[OK] GTFS cargado: {len(b.stops)} stops, {len(b.routes)} routes, "
          f"{len(b.trips)} trips, {len(b.stop_times)} stop_times, {len(b.shapes)} shapes")
    # prueba del caso >24:00 (criterio Plan B paso 2.1)
    assert parse_gtfs_time("24:20:00") == pd.Timedelta(hours=24, minutes=20)
    assert parse_gtfs_time("25:05:30") == pd.Timedelta(hours=25, minutes=5, seconds=30)
    print("[OK] parse_gtfs_time soporta horas >= 24 (viajes nocturnos)")
