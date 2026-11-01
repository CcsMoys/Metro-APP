"""gtfs_export.py — Convierte data/processed/network.json a un paquete GTFS estático.

Genera: agency.txt, calendar.txt, routes.txt, stops.txt, trips.txt, stop_times.txt, shapes.txt

Estrategia (Plan Integrado, Paso 1.2):
- Sin geometría oficial de vía: cada shape se construye conectando las paradas de la
  línea en orden (`stops_ordered`) y densificando con interpolación lineal.
- Horarios sintéticos creíbles por headway según modo; servicio 05:00-23:30.
- Tiempos escritos como HH:MM:SS (el loader soporta >24:00 si hiciera falta).
"""
from __future__ import annotations

import csv
import json
import math
import os
from datetime import timedelta

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
NETWORK_PATH = os.path.join(ROOT, "data", "processed", "network.json")
GTFS_DIR = os.path.join(ROOT, "backend", "data", "gtfs")

HEADWAY_MIN = {"metro": 4, "rail": 12, "cable_car": 8, "gondola": 10, "bus": 10}
AVG_SPEED_KMH = {"metro": 35.0, "rail": 60.0, "cable_car": 16.0, "gondola": 16.0, "bus": 22.0}
ROUTE_TYPE = {"metro": "1", "rail": "2", "cable_car": "6", "gondola": "6", "bus": "3"}
SERVICE_START = 5 * 60          # 05:00
SERVICE_END = 23 * 60 + 30      # 23:30


def haversine_km(lat1, lon1, lat2, lon2):
    r = 6371.0088
    p1, p2 = math.radians(lat1), math.radians(lat2)
    a = (math.sin((p2 - p1) / 2) ** 2
         + math.cos(p1) * math.cos(p2) * math.sin(math.radians(lon2 - lon1) / 2) ** 2)
    return 2 * r * math.asin(math.sqrt(a))


def densify(points, step_deg=0.002):
    """Interpolación lineal sobre [lon,lat] para shapes suaves."""
    out = [points[0]]
    for a, b in zip(points, points[1:]):
        n = max(1, int(math.hypot(b[0] - a[0], b[1] - a[1]) / step_deg))
        for i in range(1, n + 1):
            f = i / n
            out.append((a[0] + (b[0] - a[0]) * f, a[1] + (b[1] - a[1]) * f))
    return out


def fmt_hms(minutes_from_midnight: float) -> str:
    total = int(round(minutes_from_midnight))
    t = timedelta(minutes=total)
    hours = t.days * 24 + t.seconds // 3600
    return f"{hours:02d}:{(t.seconds % 3600) // 60:02d}:00"


def load_network(path=NETWORK_PATH):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def iter_lines(network):
    """Yield dicts normalizados: id, name, mode, color, stops_ordered."""
    for sys_key, sys in network["systems"].items():
        meta = sys.get("system", {})
        stype = meta.get("type", "metro")
        for ln in sys.get("lines", []):
            if ln.get("status") not in (None, "operational", "open", "opened"):
                # conservar solo operacionales; campos variables
                pass
            mode = stype if stype in ROUTE_TYPE else ("rail" if "ferro" in sys_key else "metro")
            yield {
                "id": ln["id"],
                "name": ln.get("long_name") or ln.get("short_name") or ln["id"],
                "mode": mode,
                "color": ln.get("color", "#888888"),
                "stops_ordered": ln.get("stops_ordered") or [],
                "system": sys_key,
            }


def build(network):
    # ids de paradas únicos por sistema (el dataset reutiliza "L1" p.ej. en MetroCable)
    stop_by_id = {}
    remap = {}
    for s in network["stops"]:
        sid = f"{s.get('system', 'x')}:{s['id']}"
        stop_by_id[sid] = s
        remap.setdefault(s["id"], []).append(sid)

    def resolve(seq_ids, system_key):
        out = []
        for i in seq_ids:
            full = f"{system_key}:{i}"
            if full in stop_by_id:
                out.append(full)
            elif i in remap and len(remap[i]) == 1:
                out.append(remap[i][0])
        return out
    rows = {"agency": [{
        "agency_id": "metrovive",
        "agency_name": "MetroVive (datos consolidados)",
        "agency_url": "https://metrodecaracas.com",
        "agency_timezone": "America/Caracas", "agency_lang": "es"}],
        "calendar": [{
        "service_id": "diario", "monday": 1, "tuesday": 1, "wednesday": 1, "thursday": 1,
        "friday": 1, "saturday": 1, "sunday": 1, "start_date": "20260101", "end_date": "20261231"}],
        "routes": [], "stops": [], "trips": [], "stop_times": [], "shapes": []}

    used_stops = set()
    seen_route_ids = set()
    for ln in iter_lines(network):
        # ids de ruta únicos (L1 existe en metro y metrocable)
        rid = f"{ln['system']}:{ln['id']}"
        if rid in seen_route_ids:
            continue
        seen_route_ids.add(rid)
        seq_ids = resolve(ln["stops_ordered"], ln["system"])
        if len(seq_ids) < 2:
            continue
        lid = rid
        rows["routes"].append({
            "route_id": lid, "agency_id": "metrovive",
            "route_short_name": lid, "route_long_name": ln["name"],
            "route_type": ROUTE_TYPE[ln["mode"]],
            "route_color": (ln["color"] or "#888888").lstrip("#")})

        pts = [(stop_by_id[i]["lon"], stop_by_id[i]["lat"]) for i in seq_ids]
        dense = densify(pts)
        cum, cum_km = [], 0.0
        for j, (lon, lat) in enumerate(dense):
            if j:
                plon, plat = dense[j - 1]
                cum_km += haversine_km(plat, plon, lat, lon)
            cum.append(cum_km)
            rows["shapes"].append({"shape_id": lid, "shape_pt_lat": f"{lat:.6f}",
                                   "shape_pt_lon": f"{lon:.6f}", "shape_pt_sequence": j})
        total_km = cum[-1]

        # distancia acumulada de cada parada (nearest point sobre dense)
        stop_dist = []
        for sid in seq_ids:
            s = stop_by_id[sid]
            k = min(range(len(dense)), key=lambda k: math.hypot(
                dense[k][0] - s["lon"], dense[k][1] - s["lat"]))
            stop_dist.append(cum[k])

        speed = AVG_SPEED_KMH[ln["mode"]]
        headway = HEADWAY_MIN[ln["mode"]]
        run_min = total_km / speed * 60 + 0.5 * len(seq_ids)

        trip_n = 0
        t = SERVICE_START
        while t + run_min <= SERVICE_END:
            directions = [(seq_ids, stop_dist),
                          (seq_ids[::-1], [total_km - d for d in stop_dist[::-1]])]
            for direction, (ids, dists) in enumerate(directions):
                trip_n += 1
                tid = f"{lid}_{trip_n:04d}"
                rows["trips"].append({
                    "route_id": lid, "service_id": "diario", "trip_id": tid,
                    "shape_id": lid, "direction_id": direction,
                    "trip_headsign": stop_by_id[ids[-1]]["name"]})
                arrive = t
                for k, sid in enumerate(ids):
                    dep = arrive + (0.5 if k < len(ids) - 1 else 0)
                    rows["stop_times"].append({
                        "trip_id": tid, "arrival_time": fmt_hms(arrive),
                        "departure_time": fmt_hms(dep), "stop_id": sid,
                        "stop_sequence": k + 1})
                    used_stops.add(sid)
                    if k + 1 < len(ids):
                        arrive = dep + abs(dists[k + 1] - dists[k]) / speed * 60
            t += headway

    for sid in sorted(used_stops):
        s = stop_by_id[sid]
        rows["stops"].append({"stop_id": sid, "stop_name": s["name"],
                              "stop_lat": f"{s['lat']:.6f}", "stop_lon": f"{s['lon']:.6f}"})
    return rows


def write_gtfs(rows, out_dir=GTFS_DIR):
    os.makedirs(out_dir, exist_ok=True)
    for name, data in rows.items():
        if not data:
            continue
        with open(os.path.join(out_dir, f"{name}.txt"), "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=list(data[0].keys()))
            w.writeheader()
            w.writerows(data)
    return out_dir


if __name__ == "__main__":
    rows = build(load_network())
    out = write_gtfs(rows)
    print(f"[OK] GTFS exportado a {out}")
    for k, v in rows.items():
        print(f"  {k}.txt: {len(v)} filas")
