#!/usr/bin/env python3
"""Paso 2: Consolidar datos del sistema ferroviario de Caracas/Venezuela.
Fuentes: xuruata/venezuela-public-transportation (canonical JSON), metrodecaracas.com, SUVE.
Salidas: network.json (grafo), geojson, sqlite, summary.json."""
import json, math, os, sqlite3, heapq

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RAW = os.path.join(BASE, "data", "raw", "xuruata", "data", "caracas")
OUT = os.path.join(BASE, "data", "processed")
os.makedirs(OUT, exist_ok=True)


def haversine(a, b):
    R = 6371.0
    la1, lo1, la2, lo2 = map(math.radians, [a["lat"], a["lon"], b["lat"], b["lon"]])
    dlat, dlo = la2 - la1, lo2 - lo1
    return round(2 * R * math.asin(math.sqrt(
        math.sin(dlat / 2) ** 2 + math.cos(la1) * math.cos(la2) * math.sin(dlo / 2) ** 2)), 4)


systems = {}
stops = {}
for sysdir in ["metro", "sistema-ferroviario", "teleferico-avila", "metrocable-sanagustin"]:
    p = lambda f: os.path.join(RAW, sysdir, f)
    if not os.path.exists(p("stops.json")):
        continue
    st = json.load(open(p("stops.json")))
    ln = json.load(open(p("lines.json")))
    sy = json.load(open(p("system.json")))
    systems[sysdir] = {"system": sy, "lines": ln}
    for s in st:
        s["system"] = sysdir
        stops[s["id"]] = s

# --- Grafo ponderado (una estación = un nodo; transbordo natural en nodos compartidos) ---
edges = []
seen = set()
for sysdir, d in systems.items():
    for line in d["lines"]:
        seq = line.get("stops_ordered", [])
        for a_id, b_id in zip(seq, seq[1:]):
            key = tuple(sorted((a_id, b_id))) + (line["id"],)
            if key in seen or a_id not in stops or b_id not in stops:
                continue
            seen.add(key)
            edges.append({"from": a_id, "to": b_id, "line": line["id"],
                          "distance_km": haversine(stops[a_id], stops[b_id]),
                          "mode": line.get("type", "metro")})

graph = {sid: [] for sid in stops}
for e in edges:
    graph[e["from"]].append({"to": e["to"], "km": e["distance_km"], "line": e["line"]})
    graph[e["to"]].append({"to": e["from"], "km": e["distance_km"], "line": e["line"]})

network = {"generated": "2026-11-02", "units": "km",
           "systems": systems, "stops": list(stops.values()), "edges": edges}
json.dump(network, open(f"{OUT}/network.json", "w"), ensure_ascii=False, indent=1)


def shortest(src, dst):
    """Dijkstra sobre el grafo multimodal."""
    dist = {src: 0}
    prev = {}
    pq = [(0, src)]
    while pq:
        d, u = heapq.heappop(pq)
        if u == dst:
            break
        if d > dist.get(u, 1e9):
            continue
        for nb in graph[u]:
            v = nb["to"]
            nd = d + nb["km"]
            if nd < dist.get(v, 1e9):
                dist[v] = nd
                prev[v] = (u, nb["line"])
                heapq.heappush(pq, (nd, v))
    if dst not in dist:
        return None
    path, cur = [], dst
    while cur != src:
        u, line = prev[cur]
        path.append({"from": u, "to": cur, "line": line})
        cur = u
    return {"total_km": round(dist[dst], 3), "hops": len(path), "path": list(reversed(path))}


r = shortest("propatria", "petare")
# Sanity: debe ser ruta directa por L1 (20 tramos), distancia geodesica ~18.2 km
# (la longitud operativa 20.4 km incluye taller/curvas; nota en docs/datos.md)
assert r and r["hops"] == 20 and all(s["line"] == "L1" for s in r["path"]), f"Control de cordura L1 fallo: {r}"
assert abs(r["total_km"] - 18.24) < 0.5, f"Distancia inesperada: {r['total_km']}"
print("[OK] Dijkstra Propatria->Petare:", r["total_km"], "km,", r["hops"], "tramos (todo L1)")
r2 = shortest("propatria", "caracas-libertador-simon-bolivar")
if r2:
    print("[OK] Ruta multi-sistema (Metro -> Estacion Tren Libertador):", r2["total_km"], "km")

# --- GeoJSON ---
fc = {"type": "FeatureCollection", "features": []}
for sysdir, d in systems.items():
    for line in d["lines"]:
        coords = [[stops[s]["lon"], stops[s]["lat"]] for s in line.get("stops_ordered", []) if s in stops]
        if len(coords) < 2:
            continue
        fc["features"].append({
            "type": "Feature",
            "properties": {"system": sysdir, "line_id": line["id"], "name": line.get("long_name"),
                           "color": line.get("color"), "type": line.get("type"),
                           "length_km": line.get("length_km")},
            "geometry": {"type": "LineString", "coordinates": coords}})
for s in stops.values():
    fc["features"].append({
        "type": "Feature",
        "properties": {"stop_id": s["id"], "name": s["name"], "system": s["system"],
                       "lines": s["lines"], "status": s.get("status")},
        "geometry": {"type": "Point", "coordinates": [s["lon"], s["lat"]]}})
json.dump(fc, open(f"{OUT}/geojson_lines_stations.json", "w"), ensure_ascii=False)

# --- SQLite ---
db_path = f"{OUT}/metro.db"
if os.path.exists(db_path):
    os.remove(db_path)
db = sqlite3.connect(db_path)
c = db.cursor()
c.executescript("""
CREATE TABLE stops(id TEXT PRIMARY KEY,name TEXT,lat REAL,lon REAL,system TEXT,status TEXT);
CREATE TABLE lines(id TEXT PRIMARY KEY,system TEXT,long_name TEXT,color TEXT,type TEXT,length_km REAL,opened TEXT);
CREATE TABLE line_stops(line_id TEXT,stop_id TEXT,seq INTEGER);
CREATE TABLE edges(from_id TEXT,to_id TEXT,line_id TEXT,distance_km REAL,mode TEXT);""")
for s in stops.values():
    c.execute("INSERT OR REPLACE INTO stops VALUES(?,?,?,?,?,?)",
              (s["id"], s["name"], s["lat"], s["lon"], s["system"], s.get("status")))
for sysdir, d in systems.items():
    for line in d["lines"]:
        c.execute("INSERT OR REPLACE INTO lines VALUES(?,?,?,?,?,?,?)",
                  (line["id"], sysdir, line.get("long_name"), line.get("color"),
                   line.get("type"), line.get("length_km"), line.get("opened")))
        for i, sid in enumerate(line.get("stops_ordered", [])):
            c.execute("INSERT INTO line_stops VALUES(?,?,?)", (line["id"], sid, i))
for e in edges:
    c.execute("INSERT INTO edges VALUES(?,?,?,?,?)",
              (e["from"], e["to"], e["line"], e["distance_km"], e["mode"]))
db.commit()
n_stops = c.execute("SELECT COUNT(*) FROM stops").fetchone()[0]
n_edges = c.execute("SELECT COUNT(*) FROM edges").fetchone()[0]
print(f"[OK] SQLite: {n_stops} estaciones, {len(systems)} sistemas, {n_edges} aristas")

# --- Resumen para notebook/documentacion ---
summary = {"systems": {}, "sample_route_propatria_petare": r}
for sysdir, d in systems.items():
    summary["systems"][sysdir] = {
        "nombre": d["system"].get("name"),
        "lineas": [{"id": l["id"], "ruta": l.get("long_name"), "color": l.get("color"),
                    "paradas": len(l.get("stops_ordered", [])), "km": l.get("length_km")}
                   for l in d["lines"]]}
json.dump(summary, open(f"{OUT}/summary.json", "w"), ensure_ascii=False, indent=1)
print("[OK] summary.json generado")
print(json.dumps(summary["systems"]["metro"]["lineas"], ensure_ascii=False, indent=1))
