# 🚇 MetroVive 3D

App (PWA Web + Android) del **Metro de Caracas y la red ferroviaria integrada de la Región Capital** (IFE Tuy Medio, Metro Los Teques, MetroCable, CableTren, BusCaracas), con:

- 🗺️ Mapa **3D en tiempo real** estilo Google Maps (MapLibre GL + Three.js, trenes animados sobre la vía)
- 🎫 **Billetera digital SUVE-like**: QR dinámico que rota cada 60 s, cifrado offline (Roja/Azul/Amarilla)
- ⭐ **MetroPuntos**: gamificación Proof-of-Travel → boletos gratis y promociones
- 🚦 Alertas de retrasos / cortes de energía · 🤖 Asistente IA local (**Ollama `llama3.2:3b`**)
- 📡 **Modo Túnel**: dead-reckoning + telemetría sintética cuando pierdes señal celular

## Estado del desarrollo (regla: cada paso se prueba antes del siguiente)

| Fase | Paso | Estado | Prueba |
|---|---|---|---|
| 1 Datos | Dataset consolidado (56 paradas, grafo Dijkstra) | ✅ | Propatria→Petare 18.24 km ✔ |
| 1 Datos | Export GTFS estático (`backend/app/gtfs_export.py`) | ✅ | 7 rutas, 3454 trips, 29892 stop_times, integridad referencial OK |
| 2 Backend | `gtfs_loader.py` (timedelta >24:00) | ✅ | asserts OK |
| 2 Backend | `position_engine.py` (interpolación Shapely) | ✅ | 54 trenes activos a las 08:00; desviación vs. vía ~0 m |
| 2 Backend | FastAPI `/api/health`, `/api/stops`, `/api/trains/positions`, `/api/routes` | ✅ | curl verificado |
| 3 Frontend | MapLibre + Three.js + InstancedMesh | 🔜 | — |
| 4 PWA | vite-plugin-pwa offline | 🔜 | — |
| 5 Docker+IA | compose + `/api/chat` Ollama | 🔜 | — |
| 6 Tickets | QR AES-256-GCM + MetroPuntos + Modo Túnel | 🔜 | — |

## Correr el backend ahora

```bash
cd backend
pip install -r requirements.txt
python -m app.gtfs_export          # regenera data/gtfs desde data/processed/network.json
uvicorn app.main:app --reload      # http://localhost:8000/docs
curl "localhost:8000/api/trains/positions?t=08:00:00"
curl "localhost:8000/api/routes?from=propatria&to=petare"
```

## Documentación
- `docs/PLAN_INTEGRADO.md` — plan maestro (fusión Plan A + Plan B, decisiones confirmadas)
- `docs/SKILLS.md` — habilidades necesarias por dominio
- `docs/repos.md` — matriz de repositorios GitHub investigados
- `notebook/MetroVive_Datos.ipynb` — centro de datos exportable

## Fuentes de datos
`xuruata/venezuela-public-transportation` (JSON/GeoJSON), mapa oficial `metrodecaracas.com/mapa`, SUVE (`suve.com.ve`). Tarifas y headways son estimaciones documentadas — verificar vigencia (preguntas abiertas §7 del plan).
