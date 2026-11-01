"""ai_chat.py — Asistente de rutas con LLM local (Fase 5).

Estrategia híbrida:
1. Si hay un servidor Ollama accesible (Ollama host configurable, por defecto
   http://localhost:11434 o http://ollama:11434 en Docker), se usa llama3.2:3b
   con function-calling hacia las herramientas reales del backend (routes/stops/
   positions) y salida JSON estricta.
2. FALLBACK determinista "sin-IA": si Ollama no está disponible (CI/GitHub
   Actions, pruebas simuladas), un motor de reglas resuelve la intención del
   mensaje (buscar parada, ruta origen→destino, estado de trenes, ayuda) usando
   directamente los datos GTFS. Esto garantiza respuestas coherentes y prueba-
   bles en cualquier entorno sin GPU ni modelos descargados.
"""
from __future__ import annotations

import json
import os
import re

OLLAMA_HOST = os.environ.get("OLLAMA_HOST", "http://localhost:11434")
OLLAMA_MODEL = os.environ.get("OLLAMA_MODEL", "llama3.2:3b")


def _ollama_available() -> bool:
    try:
        import httpx
        r = httpx.get(f"{OLLAMA_HOST}/api/tags", timeout=2.0)
        return r.status_code == 200
    except Exception:
        return False


SYSTEM_PROMPT = """Eres el asistente de movilidad de MetroVive para el Metro de Caracas,
Metro Los Teques, IFE Tuy Medio, MetroCable, CableTren y BusCaracas.
Datos disponibles: red GTFS multimodal de la Región Capital de Venezuela.
Responde SIEMPRE en español y en JSON estricto con claves:
{"reply": str, "route": {...}|null, "confidence": 0..1}
Nunca inventes estaciones: usa solo las provided en el contexto."""


def ask_ollama(message: str, context: str) -> dict | None:
    try:
        import httpx
        payload = {
            "model": OLLAMA_MODEL,
            "stream": False,
            "format": "json",
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": f"Contexto de red: {context}\nPregunta: {message}"},
            ],
            "options": {"temperature": 0.1},
        }
        r = httpx.post(f"{OLLAMA_HOST}/api/chat", json=payload, timeout=60.0)
        if r.status_code != 200:
            return None
        content = r.json()["message"]["content"]
        return json.loads(content)
    except Exception:
        return None


# ------------------------- Fallback determinista ---------------------------- #

STOP_RE = re.compile(r"\b([A-Za-zÁÉÍÓÚáéíóúñÑ]+(?:\s+[A-Za-zÁÉÍÓÚáéíóúñÑ]+){0,2})\b")


def _match_stop(name: str, stops: dict) -> str | None:
    name_n = _norm(name)
    best, best_score = None, 0.0
    for sid, s in stops.items():
        sn = _norm(s["name"])
        if name_n == sn:
            return sid
        if name_n and (name_n in sn or sn.startswith(name_n)):
            score = len(name_n) / max(len(sn), 1)
            if score > best_score:
                best, best_score = sid, score
    return best


def _norm(x: str) -> str:
    x = x.lower().strip()
    for a, b in (("á", "a"), ("é", "e"), ("í", "i"), ("ó", "o"), ("ú", "u"), ("ñ", "n")):
        x = x.replace(a, b)
    return x


def rule_engine(message: str, network_ctx: dict) -> dict:
    """Intenciones soportadas: help | find_stop | route | status."""
    msg = _norm(message)
    stops = network_ctx["stops"]          # {id: {name}}
    reply, route, conf = "", None, 0.9

    m = re.search(r"(?:de|desde)\s+(.+?)\s+(?:hacia|a|para|hasta)\s+(.+?)[?\!.]*$", message, re.I)
    if m and any(k in msg for k in ("llego", "ruta", "viaje", "voy", "ir", "como")):
        src = _match_stop(m.group(1), stops)
        dst = _match_stop(m.group(2), stops)
        if src and dst:
            route = network_ctx["route_fn"](src, dst)
            if route:
                legs_txt = " → ".join(
                    f"{l['from_name']}({l['mode']})" for l in route["legs"]) + \
                    f" → {route['legs'][-1]['to_name']}"
                reply = (f"Ruta sugerida: {legs_txt}. Distancia total "
                         f"{route['total_km']} km.")
                conf = 0.95
            else:
                reply = "No encontré una ruta entre esas paradas."
                conf = 0.6
        else:
            miss = [g for g in (m.group(1), m.group(2)) if not _match_stop(g, stops)]
            reply = f"No reconozco la(s) estación(es): {', '.join(miss)}."
            conf = 0.7
    elif any(k in msg for k in ("estacion", "parada", "donde queda", "dónde queda")):
        m2 = re.search(r"[\"']([^\"']+)[\"']", message)
        term = _norm(m2.group(1)) if m2 else re.sub(
            r"(busca|donde esta|donde queda|dónde está|dónde queda|dónde esta|estacion|parada)",
            "", msg).strip()
        sid = _match_stop(term, stops) if term else None
        if sid:
            s = stops[sid]
            reply = f"{s['name']} existe en la red (id: {sid})."
        else:
            reply = "Dime el nombre de una estación, p.ej. '¿Dónde está \"Zona Rental\"?'."
            conf = 0.5
    elif any(k in msg for k in ("ayuda", "help", "que puedes", "qué puedes")):
        reply = ("Puedo: 1) calcular rutas ('¿Cómo llego de Propatria a Cúa?'), "
                 "2) buscar estaciones ('¿Dónde está Altamira?'), "
                 "3) reportar trenes activos ('estado').")
        conf = 1.0
    elif "estado" in msg or "trenes" in msg:
        n = network_ctx["train_count"]
        reply = f"En este instante hay {n} trenes circulando en la red integrada."
        conf = 1.0
    else:
        reply = ("No entendí la consulta. Prueba: '¿Cómo llego de Capitolio a Zona Rental?' "
                 "o 'estado' para ver trenes activos.")
        conf = 0.4

    return {"reply": reply, "route": route, "confidence": conf}


def chat(message: str, network_ctx: dict) -> dict:
    """Entrypoint principal: intenta Ollama, cae al motor de reglas."""
    used_llm = False
    if _ollama_available():
        ctx_small = {k: v for k, v in network_ctx.items() if k != "route_fn"}
        ans = ask_ollama(message, json.dumps(list(ctx_small["stops"].values())[:80],
                                             ensure_ascii=False))
        if ans and "reply" in ans:
            ans.setdefault("route", None)
            ans["engine"] = f"ollama:{OLLAMA_MODEL}"
            return ans
    out = rule_engine(message, network_ctx)
    out["engine"] = "rule-fallback"
    return out
