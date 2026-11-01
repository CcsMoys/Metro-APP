"""main.py — API FastAPI de MetroVive (Fase 2, Paso 2.3).

Endpoints:
- GET /api/health
- GET /api/stops                          -> paradas del GTFS
- GET /api/trains/positions?t=HH:MM:SS    -> trenes interpolados (vacío => ahora)
- GET /api/routes?from=&to=               -> Dijkstra multimodal sobre network.json
"""
from __future__ import annotations

import heapq
import json
import os

from fastapi import FastAPI, HTTPException, Query

from .position_engine import PositionEngine

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
NETWORK_PATH = os.path.join(ROOT, "data", "processed", "network.json")

app = FastAPI(title="MetroVive API", version="0.1.0")


@app.on_event("startup")
def _startup():
    app.state.engine = PositionEngine()
    with open(NETWORK_PATH, encoding="utf-8") as f:
        net = json.load(f)
    app.state.network = net
    # grafo para ruteo
    graph: dict[str, list[tuple[str, float, str]]] = {}
    for e in net["edges"]:
        a, b = e["from"], e["to"]
        w = e["distance_km"]
        mode = e.get("mode", "via")
        pen = 0.4 if mode == "walk" else 0.0  # penalización fija por transbordo a pie
        graph.setdefault(a, []).append((b, w + pen, mode))
        graph.setdefault(b, []).append((a, w + pen, mode))
    app.state.graph = graph
    app.state.stops_by_id = {s["id"]: s for s in net["stops"]}


@app.get("/api/health")
def health():
    eng: PositionEngine = app.state.engine
    return {"status": "ok", "segments": int(len(eng.segments)),
            "shapes": len(eng.shapes), "routes": int(len(eng.bundle.routes))}


@app.get("/api/stops")
def stops():
    return app.state.engine.bundle.stops.to_dict(orient="records")


@app.get("/api/trains/positions")
def trains_positions(t: str = Query("", description="HH:MM:SS; vacío = ahora")):
    eng: PositionEngine = app.state.engine
    try:
        return {"time": t or "now", "trains": eng.at_time(t) if t else eng.now()}
    except ValueError:
        raise HTTPException(400, "formato de tiempo inválido, use HH:MM:SS")


def dijkstra(graph, src, dst):
    dist = {src: 0.0}
    prev = {}
    pq = [(0.0, src)]
    while pq:
        d, u = heapq.heappop(pq)
        if d > dist.get(u, 1e18):
            continue
        if u == dst:
            break
        for v, w, mode in graph.get(u, []):
            nd = d + w
            if nd < dist.get(v, 1e18):
                dist[v] = nd
                prev[v] = (u, w, mode)
                heapq.heappush(pq, (nd, v))
    if dst not in dist:
        return None
    path, cur = [], dst
    while cur in prev:
        u, w, mode = prev[cur]
        path.append({"from": u, "to": cur, "cost_km": round(w, 3), "mode": mode})
        cur = u
    return {"origin": src, "destination": dst, "total_km": round(dist[dst], 3),
            "legs": list(reversed(path))}


@app.get("/api/routes")
def routes(_from: str = Query(..., alias="from"), to: str = Query(...)):
    stops = app.state.stops_by_id
    for sid in (_from, to):
        if sid not in stops:
            # permitir búsqueda por nombre aproximado
            match = [k for k, s in stops.items() if s["name"].lower().startswith(sid.lower())]
            if len(match) == 1:
                if sid == _from:
                    _from = match[0]
                else:
                    to = match[0]
                continue
            raise HTTPException(404, f"parada desconocida: {sid}")
    r = dijkstra(app.state.graph, _from, to)
    if r is None:
        raise HTTPException(404, "no hay ruta entre esas paradas")
    # enriquecer nombres
    for leg in r["legs"]:
        leg["from_name"] = stops[leg["from"]]["name"]
        leg["to_name"] = stops[leg["to"]]["name"]
    return r
