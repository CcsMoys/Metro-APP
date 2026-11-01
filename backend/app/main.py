"""main.py — API FastAPI de MetroVive (Fase 2, Paso 2.3).

Endpoints:
- GET /api/health
- GET /api/stops                          -> paradas del GTFS
- GET /api/trains/positions?t=HH:MM:SS    -> trenes interpolados (vacío => ahora)
- GET /api/routes?from=&to=               -> Dijkstra multimodal sobre network.json
- POST /api/chat                          -> asistente IA (Ollama + fallback reglas)
- POST /api/tunnel/start|tick|stop        -> telemetría sintética Modo Túnel
- POST /api/users, GET /api/users/{id}    -> billetera SUVE + MetroPuntos
- POST /api/trips                         -> registrar viaje (prueba de trayecto)
- POST /api/redeem                        -> canjear puntos
- GET  /api/qr/{uid}                      -> QR dinámico AES-GCM (60 s)
- POST /api/qr/validate                   -> simulador de torniquete
"""
from __future__ import annotations

import heapq
import json
import os

from fastapi import FastAPI, HTTPException, Query
from pydantic import BaseModel

from .position_engine import PositionEngine
from .tunnel_mode import TunnelEngine
from . import loyalty, ai_chat

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
NETWORK_PATH = os.path.join(ROOT, "data", "processed", "network.json")

app = FastAPI(title="MetroVive API", version="0.1.0")


@app.on_event("startup")
def _startup():
    app.state.engine = PositionEngine()
    app.state.tunnel = TunnelEngine(app.state.engine)
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
    # normalizar ids: aceptar "metro:propatria" == "propatria"
    def resolve(sid: str) -> str | None:
        if sid in stops:
            return sid
        bare = sid.split(":")[-1]
        if bare in stops:
            return bare
        match = [k for k, s in stops.items() if s["name"].lower().startswith(sid.lower())]
        return match[0] if len(match) == 1 else None

    src = resolve(_from)
    dst = resolve(to)
    if src is None or dst is None:
        missing = _from if src is None else to
        raise HTTPException(404, f"parada desconocida: {missing}")
    r = dijkstra(app.state.graph, src, dst)
    if r is None:
        raise HTTPException(404, "no hay ruta entre esas paradas")
    # enriquecer nombres
    for leg in r["legs"]:
        leg["from_name"] = stops[leg["from"]]["name"]
        leg["to_name"] = stops[leg["to"]]["name"]
    return r


# ============================ Fase 5: Chat IA =============================== #

class ChatRequest(BaseModel):
    message: str


@app.post("/api/chat")
def chat(req: ChatRequest):
    def route_fn(src, dst):
        r = dijkstra(app.state.graph, src, dst)
        if r:
            for leg in r["legs"]:
                leg["from_name"] = app.state.stops_by_id[leg["from"]]["name"]
                leg["to_name"] = app.state.stops_by_id[leg["to"]]["name"]
        return r

    ctx = {
        "stops": app.state.stops_by_id,
        "route_fn": route_fn,
        "train_count": len(app.state.engine.now()),
    }
    return ai_chat.chat(req.message, ctx)


# ========================= Fase 6: Modo Túnel =============================== #

class TunnelStart(BaseModel):
    trip_id: str | None = None
    t: str | None = None


class TunnelSessionId(BaseModel):
    session_id: str


@app.post("/api/tunnel/start")
def tunnel_start(req: TunnelStart):
    try:
        return app.state.tunnel.start(req.trip_id, req.t)
    except (KeyError, RuntimeError) as e:
        raise HTTPException(400, str(e))


@app.post("/api/tunnel/tick")
def tunnel_tick(req: TunnelSessionId):
    try:
        return app.state.tunnel.tick(req.session_id)
    except KeyError as e:
        raise HTTPException(404, str(e))


@app.post("/api/tunnel/stop")
def tunnel_stop(req: TunnelSessionId):
    return app.state.tunnel.stop(req.session_id)


@app.get("/api/tunnel/sessions")
def tunnel_sessions():
    return {"sessions": app.state.tunnel.active()}


# ==================== Fase 6: Billetera SUVE + MetroPuntos ================== #

class UserCreate(BaseModel):
    name: str
    card_type: str = "roja"


class TripCreate(BaseModel):
    user_id: int
    from_stop: str
    to_stop: str


class RedeemCreate(BaseModel):
    user_id: int
    kind: str  # free_ticket | discount_50


class QRValidate(BaseModel):
    token: str
    user_name: str


@app.post("/api/users")
def users_create(req: UserCreate):
    try:
        return loyalty.create_user(req.name, req.card_type)
    except ValueError as e:
        raise HTTPException(400, str(e))


@app.get("/api/users/{uid}")
def users_get(uid: int):
    try:
        return loyalty.get_user(uid)
    except KeyError:
        raise HTTPException(404, "usuario no existe")


@app.post("/api/trips")
def trips_create(req: TripCreate):
    def resolve(sid: str) -> str | None:
        stops = app.state.stops_by_id
        if sid in stops:
            return sid
        bare = sid.split(":")[-1]
        return bare if bare in stops else None

    src, dst = resolve(req.from_stop), resolve(req.to_stop)
    if not src or not dst:
        raise HTTPException(404, "parada desconocida")
    r = dijkstra(app.state.graph, src, dst)
    if r is None:
        raise HTTPException(404, "no hay ruta entre esas paradas")
    try:
        res = loyalty.register_trip(req.user_id, req.from_stop, req.to_stop,
                                    r["total_km"], r["legs"])
        res["route"] = r
        return res
    except (ValueError, KeyError) as e:
        raise HTTPException(400, str(e))


@app.post("/api/redeem")
def redeem(req: RedeemCreate):
    try:
        return loyalty.redeem(req.user_id, req.kind)
    except ValueError as e:
        raise HTTPException(400, str(e))


@app.get("/api/qr/{uid}")
def qr_get(uid: int):
    try:
        return loyalty.generate_qr(uid)
    except KeyError:
        raise HTTPException(404, "usuario no existe")


@app.post("/api/qr/validate")
def qr_validate(req: QRValidate):
    return loyalty.validate_qr(req.token, req.user_name)
