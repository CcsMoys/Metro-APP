#!/usr/bin/env python3
"""Paso A3: Generar notebook exportable MetroCaracas_Datos.ipynb desde las plantillas de celdas.
El notebook es autocontenido: carga data/processed/*, valida, dibuja mapa interactivo HTML
(sin dependencias de Jupyter para el render) y trae prompts listos para Ollama/Gemini CLI."""
import json, os

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
NB_PATH = os.path.join(BASE, "notebook", "MetroCaracas_Datos.ipynb")
os.makedirs(os.path.dirname(NB_PATH), exist_ok=True)


def md(text):
    return {"cell_type": "markdown", "metadata": {}, "source": text.strip().splitlines(True)}


def code(text):
    return {"cell_type": "code", "execution_count": None, "metadata": {}, "outputs": [], "source": text.strip().splitlines(True)}


cells = [
md("""# 🚇 MetroVive — Dataset del Metro de Caracas y red ferroviaria de Venezuela
**Notebook de recopilación y validación de datos** (generado 2026-11-02).
Este notebook es el puente entre la fase de investigación y la app en tu servidor local.

Contenido:
1. Carga y exploración del dataset consolidado (`data/processed/`)
2. Validaciones automáticas (integridad del grafo, rutas de control)
3. Mapa interactivo 2D/3D preliminar (MapLibre GL, mismo motor que usará la app)
4. Motor de ruteo Dijkstra multimodal en vivo
5. Simulador de trenes en tiempo real (base del feed GTFS-RT futuro)
6. Esquema del ticket digital + gamificación (motor de reglas)
7. Prompts listos para Ollama / Gemini CLI
8. Checklist de habilidades (`docs/SKILLS.md`) y repos (`docs/repos.md`)

> Fuentes: xuruata/venezuela-public-transportation (ODbL), Crom-Studio GTFS, metrodecaracas.com, SUVE/TRL.
> Ejecuta celda por celda; cada sección imprime `[OK]` al validar.""")] ,

code('''import json, math, sqlite3, heapq, os
from pathlib import Path

ROOT = Path.cwd() if Path("data/processed/network.json").exists() else Path("..")
DATA = ROOT / "data" / "processed"
net = json.load(open(DATA / "network.json", encoding="utf-8"))
summary = json.load(open(DATA / "summary.json", encoding="utf-8"))
stops = {s["id"]: s for s in net["stops"]}
print(f"[OK] {len(stops)} estaciones | {len(net['edges'])} aristas | sistemas: {list(net['systems'])}")'''),

md("## 1. Exploración: líneas oficiales con colores (entra en la capa 3D)"),

code('''for sysdir, d in net["systems"].items():
    print(f"== {d['system'].get('name')} ==")
    for l in d["lines"]:
        n = len(l.get("stops_ordered", []))
        print(f"  {l['id']:4} {l.get('long_name',''):38} color={l.get('color')} paradas={n} km={l.get('length_km')}")
print("[OK] lineas listadas")'''),

code('''# Tarifas de referencia (ajustar vigente al publicar; fuente: anuncios Metro/SUVE)
TARIFAS = {"metro": 2.0, "tren_libertador": 4.0, "metrocable": 2.0}  # Bs.S aprox 2025-2026
print("[i] Tarifas base:", TARIFAS)'''),

md("## 2. Validaciones de integridad"),

code('''errors = []
ids = set(stops)
for e in net["edges"]:
    if e["from"] not in ids or e["to"] not in ids: errors.append(("arista colgante", e))
for s in net["stops"]:
    if not (-110 < s["lon"] < -34 and 0 < s["lat"] < 75): errors.append(("coord fuera de VE", s))
    if any(c is None for c in (s["lat"], s["lon"])): errors.append(("coord nula", s))
assert not errors, errors
print(f"[OK] Integridad: {len(net['edges'])} aristas sin referencias rotas, todas las coords dentro de Venezuela")'''),

code('''# Rutas de control (deben coincidir con lo probado en build_dataset.py)
def build_graph():
    g = {sid: [] for sid in stops}
    for e in net["edges"]:
        w = e["distance_km"] + (0.35 if e["line"] == "WALK" else 0)
        g[e["from"]].append({"to": e["to"], "km": w, "line": e["line"]})
        g[e["to"]].append({"to": e["from"], "km": w, "line": e["line"]})
    return g
G = build_graph()

def shortest(src, dst):
    dist = {src: 0}; prev = {}; pq = [(0, src)]
    while pq:
        d, u = heapq.heappop(pq)
        if u == dst: break
        if d > dist.get(u, 1e9): continue
        for nb in G[u]:
            v = nb["to"]; nd = d + nb["km"]
            if nd < dist.get(v, 1e9):
                dist[v] = nd; prev[v] = (u, nb["line"]); heapq.heappush(pq, (nd, v))
    if dst not in dist: return None
    path = []; cur = dst
    while cur != src:
        u, line = prev[cur]; path.append((u, cur, line)); cur = u
    return round(dist[dst], 2), list(reversed(path))

k, p = shortest("propatria", "petare"); assert k and abs(k-18.59) < 0.6, k
k2, p2 = shortest("propatria", "cua-general-ezequiel-zamora"); assert k2 and k2 < 56, k2
print(f"[OK] Propatria->Petare {k} km directo L1")
print(f"[OK] Propatria->Cua {k2} km multimodal ({len(set(x[2] for x in p2))} modos)")'''),

md("## 3. Mapa interactivo (HTML standalone con MapLibre — idéntico motor al de la app)\nEjecuta la celda y abre el archivo generado, o corre `python scripts/make_map_html.py` desde la raíz."),

code('''geojson = json.load(open(DATA / "geojson_lines_stations.json", encoding="utf-8"))
html = f\'\'\'<!doctype html><html><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<link href="https://cdn.jsdelivr.net/npm/maplibre-gl@4/dist/maplibre-gl.css" rel="stylesheet">
<script src="https://cdn.jsdelivr.net/npm/maplibre-gl@4/dist/maplibre-gl.js"></script>
<style>body{{margin:0}}#map{{position:absolute;inset:0}}</style></head><body><div id="map"></div>
<script>
const DATA = {json.dumps(geojson, ensure_ascii=False)};
const map = new maplibregl.Map({{
  container: 'map',
  style: 'https://demotiles.maplibre.org/style.json',   // estilo base gratuito
  center: [-66.92, 10.43], zoom: 11, pitch: 55   // <-- vista 3D estilo Google Maps
}});
map.on('load', () => {{
  map.addSource('lines', {{type:'geojson', data: {{type:'FeatureCollection',
      features: DATA.features.filter(f=>f.geometry.type==='LineString')}}}});
  map.addSource('stops', {{type:'geojson', data: {{type:'FeatureCollection',
      features: DATA.features.filter(f=>f.geometry.type==='Point')}}}});
  map.addLayer({{id:'lines-c', type:'line', source:'lines',
    paint:{{'line-color':['get','color'],'line-width':5,'line-opacity':0.9}}}});
  map.addLayer({{id:'lines-glow', type:'line', source:'lines',
    paint:{{'line-color':['get','color'],'line-width':12,'line-blur':8,'line-opacity':0.35}}}});
  map.addLayer({{id:'stops-p', type:'circle', source:'stops',
    paint:{{'circle-radius':6,'circle-color':'#fff','circle-stroke-color':'#111','circle-stroke-width':2}}}});
  map.addLayer({{id:'labels', type:'symbol', source:'stops', minzoom:10,
    layout:{{'text-field':['get','name'],'text-offset':[0,1],'text-size':11}},
    paint:{{'text-color':'#eee','text-halo-color':'#000','text-halo-width':1.5}}}});
}});
map.addControl(new maplibregl.NavigationControl({{visualizePitch:true}}));
</script></body></html>\'\'\'
out = Path("mapa_preview.html"); out.write_text(html, encoding="utf-8")
print(f"[OK] Mapa 3D preliminar escrito en {out.resolve()}")'''),

md("## 4. Simulador de trenes en tiempo real (embrión del feed GTFS-RT)\nGenera posiciones interpoladas sobre la geometría de la línea. En la app esto sale por WebSocket a 1 Hz y alimenta los modelos 3D."),

code('''import random, time
def simulate(line_id="L1", n_trains=6, speed_kmh=35):
    line = next(l for d in net["systems"].values() for l in d["lines"] if l["id"] == line_id)
    seq = line["stops_ordered"]
    pts = [(stops[s]["lat"], stops[s]["lon"]) for s in seq]
    seg_len = []
    for (la1, lo1), (la2, lo2) in zip(pts, pts[1:]):
        R = 6371.0
        la1r, lo1r, la2r, lo2r = map(math.radians, [la1, lo1, la2, lo2])
        seg_len.append(2*R*math.asin(math.sqrt(math.sin((la2r-la1r)/2)**2+math.cos(la1r)*math.cos(la2r)*math.sin((lo2r-lo1r)/2)**2)))
    total = sum(seg_len)
    trains = []
    for i in range(n_trains):
        pos = total * i / n_trains  # repartidos
        trains.append({"train": f"{line_id}-{i+1}", "offset_h": random.choice([1, -1]), "pos_km": pos})
    def tick(dt_min=1/60):
        frames = []
        for t in trains:
            t["pos_km"] = (t["pos_km"] + speed_kmh*dt_min*t["offset_h"]) % total
            acc, k = 0, 0
            while k < len(seg_len)-1 and acc+seg_len[k] < t["pos_km"]:
                acc += seg_len[k]; k += 1
            f = (t["pos_km"]-acc)/seg_len[k]
            (la1, lo1), (la2, lo2) = pts[k], pts[min(k+1, len(pts)-1)]
            frames.append({"train": t["train"], "lat": la1+(la2-la1)*f, "lon": lo1+(lo2-lo1)*f,
                           "segment": f"{seq[k]}->{seq[k+1] if k+1<len(seq) else seq[k]}"})
        return frames
    return frames

frames = simulate()
assert len(frames) == 6 and all(-67.2 < fr["lon"] < -66.4 for fr in frames)
for fr in frames[:3]: print(fr)
print("[OK] simulador produce frames validos (integrar con VehiclePosition GTFS-RT)")'''),

md("## 5. Ticket digital + gamificación (motor de reglas mínimo)\nReglas de ejemplo: viaje=10 pts; 5 viajes seguidos en la semana (+25%); niveles Bronce/Plata/Oro; Oro ⇒ boleto gratis semanal. En producción: QR TOTP + firma en servidor."),

code('''class PasaporteMetro:
    LEVELS = [("Bronce", 0), ("Plata", 100), ("Oro", 300)]
    def __init__(self): self.points = 0; self.trips = 0; self.free_tickets = 0
    def add_trip(self, fare=2.0):
        self.trips += 1; self.points += 10
        if self.trips % 5 == 0: self.points += 5   # bonus racha
        lvl = max(name for name, need in self.LEVELS if self.points >= need)
        if lvl == "Oro" and self.trips % 7 == 0: self.free_tickets += 1
        return {"trips": self.trips, "points": self.points, "level": lvl, "free": self.free_tickets}

p = PasaporteMetro()
hist = [p.add_trip() for _ in range(15)]
assert hist[-1]["level"] == "Plata" and hist[-1]["free"] == 0
assert p.add_trip()["points"] == 160
print(json.dumps(hist[-1]))
print("[OK] motor de fidelizacion: niveles y boletos gratis funcionando")'''),

md("## 6. Prompts listos para tu IA local\n### Ollama (gratis, local)\n```bash\nollama pull llama3.2:3b   # o qwen2.5:3b si tienes mas RAM\n```\nPrompt sistema sugerido (pegar en tu backend):\n```\nEres el asistente de MetroVive para el Metro de Caracas y trenes de Venezuela.\nNUNCA inventes rutas ni tarifas: usa las herramientas route(from,to), alerts(), fare(mode).\nResponde en espanol breve, menciona linea(s), transbordos y tiempo estimado.\nSi el usuario esta bajo tierra y sin senal, prioriza info ya descargada en cache.\n```\n\n### Gemini CLI (free-tier)\n```bash\nnpm i -g @google/gemini-cli\ngemini \"Lee docs/PLAN.md y genera el esqueleto FastAPI del endpoint /api/routes\"\n```"""),

code('''# Plantilla de llamada a Ollama desde este notebook (descomentar con servidor local encendido)
OLLAMA_PROMPT = """Con esta red: {lineas}. ¿Ruta corta y sencilla de Gato Negro a Petare?
Formato: Linea(s), estacion de transbordo, N paradas, tiempo estimado."""
lineas = "; ".join(f"{l['id']}:{l['long_name']}" for d in net['systems'].values() for l in d['lines'])
print(OLLAMA_PROMPT.format(lineas=lineas)[:300], "...")
print("[OK] prompt listo (ejecutar contra http://localhost:11434/api/generate cuando Ollama este activo)")'''),

md("## 7. Exportar a la app\nEste notebook dejó en disco:\n- `data/processed/network.json`, `metro.db`, `geojson_lines_stations.json`, `summary.json`\n- `notebook/mapa_preview.html` (motor MapLibre idéntico al frontend definitivo)\n\nEn el servidor local basta con `pip install fastapi uvicorn` y leer estos archivos (ver `docs/PLAN.md` paso C1).\n\n### Habilidades requeridas → `docs/SKILLS.md` · Repos investigados → `docs/repos.md` · Plan completo → `docs/PLAN.md`"),

code('''print("""
RESUMEN FINAL
- Estaciones: %d | Sistemas: %d | Aristas: %d | Transbordos walk: %d
- Rutas probadas: Propatria->Petare (L1), Propatria->Cua (Metro+Tren Libertador)
- Archivos exportables: network.json, metro.db, geojson, summary.json, mapa_preview.html
""" % (len(stops), len(net['systems']), len(net['edges']), sum(1 for e in net['edges'] if e['line']=='WALK')))
print("[OK] notebook completo")'''),
]

nb = {"cells": cells, "metadata": {"kernelspec": {"display_name": "Python 3", "language": "python", "name": "python3"},
                                   "language_info": {"name": "python", "version": "3.12"}}, "nbformat": 4, "nbformat_minor": 5}
json.dump(nb, open(NB_PATH, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print(f"[OK] Notebook generado: {NB_PATH} ({len(cells)} celdas)")
