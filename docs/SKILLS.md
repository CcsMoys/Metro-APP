# 🧩 Habilidades (skills) necesarias para construir MetroVive

Organizadas por dominio. Cada una incluye: **qué es**, **cómo se practica en este proyecto** y **recurso gratis**.

## 1. Datos geoespaciales y GTFS
- **GeoJSON / WGS84 / sistemas de coordenadas** → cargar `geojson_lines_stations.json`, entender `[lon, lat]`.
- **GTFS estático** (`stops.txt`, `routes.txt`, `trips.txt`, `stop_times.txt`, `shapes.txt`, `frequencies.txt`) → convertir nuestro dataset a GTFS publicable.
- **GTFS-Realtime (protobuf)** → feed de `TripUpdate` (retrasos), `VehiclePosition` (trenes en vivo), `ServiceAlert` (cortes de energía).
- Recurso: gtfs.org + tutorial `gtfs-realtime-bindings` (Python/JS).

## 2. Backend Python (FastAPI)
- CRUD + endpoints de ruteo; SQLite embebido (luego Postgres+PostGIS si crece).
- Pydantic para validación; `pytest` + `httpx.AsyncClient` para pruebas.
- Autenticación ligera (JWT/OAuth2 password) para billetera de tickets.
- Firmado HMAC/ed25519 de boletos (evitar fraude offline).

## 3. Frontend web moderna (la app es PWA)
- **HTML/CSS/JS o React/Svelte** — un solo código para celular y escritorio.
- **PWA**: manifest, Service Worker (Workbox), IndexedDB (Dexie.js), modo offline total.
- Responsive mobile-first, touch gestures, dark mode.

## 4. Mapas y visualización 3D
- **MapLibre GL JS**: capas GeoJSON, estilos vectoriales, `flyTo/pitch/bearing`, fuentes dinámicas.
- **three.js + overlay de MapLibre** (o capa `CustomLayer`): modelo glTF del tren, iluminación, túneles extruidos, animación con `tween.js`/slerp sobre la polilínea.
- Matemática básica 3D: proyeccion lat/lon -> coordenadas locales (Mercator), quaternion para orientación del tren.
- Alternativa pesada: CesiumJS (globo real).

## 5. Tiempo real y telemetría
- **WebSocket / SSE** para empujar posiciones de trenes al cliente (1 Hz).
- Simulación física simple: velocidad media por tramo, dwell time en estación, jitter por "retraso".
- Dead-reckoning en el teléfono (GPS -> acelerometro/barómetro) para seguir estimando posición bajo tierra.
- Opcional avanzado: beacons BLE iBeacon en estaciones (NRF52 ~$5/placa) — fase "hardware".

## 6. Ticketing digital y gamificación
- QR dinámico tipo TOTP (`pyotp`), ventana de validez 60 s, anti-captura de pantalla (flags Android `FLAG_SECURE`).
- Motor de reglas: viajes→puntos→niveles→cupones (tabla `rewards`), expiración, anti-fraude (límites por dispositivo/servidor).
- Pasarela de pago venezolana (PagoEfectivo, Banesca Madison, Zin… vía API o QR de pago) — fase monetización.

## 7. IA local (Ollama / Gemini CLI)
- Desplegar modelos gratis: `ollama pull llama3.2:3b`; API `POST /api/chat`.
- **Function calling / tools**: que el LLM consulte `/api/routes` y `/api/alerts` en vez de inventar.
- RAG mínimo: embeddings locales (`nomic-embed-text`) sobre alertas + FAQ del metro.
- Prompt engineering en español venezolano; evaluación con golden-set.
- Gemini CLI como copiloto de desarrollo (gratis con cuenta Google).

## 8. DevOps y servidor local
- Docker + docker-compose (backend, frontend/nginx, ollama).
- HTTPS local (mkcert), backups del SQLite, CI básico (GitHub Actions corre los tests del dataset).
- Monitoreo simple: Uptime Kuma.

## 9. Legal y datos abiertos (Venezuela)
- Licencia ODbL del dataset xuruata → atribución obligatoria si redistribuimos.
- Uso de marcas "Metro de Caracas"/logos: fines informativos vs comercial → consultar antes de monetizar.
- Protección de datos del usuario (geolocalización): minimizar, almacenar local, cifrar.

## 10. Testing y calidad
- pytest (ruteo, tickets), Playwright (flujos web), Lighthouse (PWA ≥90), pruebas en modo avión.
- Control de versiones: ramas por feature, commits por paso probado (ya activo en este repo).

### Matriz habilidad → paso del plan
| Habilidad | Paso donde se usa |
|---|---|
| GeoJSON/GTFS | A2, A3, C1 |
| FastAPI | C1 |
| PWA/offline | C2 |
| MapLibre/three.js | C2, C4 |
| WebSocket/simulación | C4 |
| QR/gamificación | C3 |
| Ollama/RAG | C5 |
| Docker | C6 |
