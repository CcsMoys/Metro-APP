# 🚇 Plan por Pasos — "MetroVive" (nombre provisional)
App + Web del Metro de Caracas y red ferroviaria de Venezuela, con mapa 3D en tiempo real, ticket digital con gamificación, telemetría de trenes y WiFi comunitario.

> **Regla del proyecto:** cada paso termina con una prueba ejecutada (`[OK]`) antes de pasar al siguiente. Al final de cada paso se hace commit.

---

## Fase A — Investigación y recopilación de datos (no se programa la app aún)

### ✅ Paso A1: Benchmark y fuentes *(HECHO)*
- Analizado el referencia **Vía Libre** (vialibre.soft-flow.app): app venezolana de rutas de transporte con mapas, paradas y planificación puerta-a-puerta. Tomamos su concepto pero ampliamos: 3D, tiempo real, ticketing y gamificación.
- Fuentes oficiales identificadas y descargadas:
  - `metrodecaracas.com/mapa/` → mapa oficial PNG/PDF (guardado en `data/raw/`).
  - `suve.com.ve` y `portal.suve.com.ve` → Tren Línea 3 / TRL / Ferrocarriles Nacionales (sitio dinámico; datos consolidados desde repos open data + Wikipedia/SUVE).
- Repos GitHub investigados (lista completa en `docs/repos.md`):
  - **xuruata/venezuela-public-transportation** ⭐ joya: JSON canónico + GeoJSON + GTFS para 10 sistemas venezolanos (Metro, TRL, Metrocable, Teleférico, Metrobús…).
  - **Crom-Studio-C-A/transporte-publico-venezuela-gtfs** → GTFS completo del Metro de Caracas.
  - Ecosistema de visualización: OpenTripPlanner, MapLibre GL JS, CesiumJS, three.js + tween.js, OsmAnd, Transit, GTFS-RT tooling.

### ✅ Paso A2: Dataset consolidado *(HECHO Y PROBADO)*
- `scripts/build_dataset.py` genera:
  - `data/processed/network.json` — grafo multimodal: **56 estaciones, 4 sistemas, 58 aristas** (incluye 7 transbordos peatonales automáticos por proximidad <800 m).
  - `data/processed/metro.db` — SQLite (stops, lines, line_stops, edges).
  - `data/processed/geojson_lines_stations.json` — capas listo para MapLibre/Cesium.
  - `data/processed/summary.json` — resumen para el notebook.
- Pruebas ejecutadas:
  - `[OK] Dijkstra Propatria→Petare: 18.24 km, 20 tramos (todo L1)` ✔ coherente con la línea real.
  - `[OK] Ruta multimodal Propatria→Cúa (Tren Libertador): 53.5 km con 1 solo transbordo` (L1→L3→camine→TL1) ✔ la penalización de transbordo funciona.
  - Transbordos detectados automáticamente: La Rinconada ↔ Caracas Libertador (92 m), Bellas Artes ↔ Parque Central Metrocable (304 m), etc.

### Paso A3: Notebook exportable *(pendiente, siguiente paso)*
- Generar `notebook/MetroCaracas_Datos.ipynb`: carga del dataset, mapa estático interactivo (Leafmap/ipywidgets o HTML standalone), validaciones y celdas listas para pegar en el servidor local.
- Incluir sección "skills" (habilidades requeridas) y prompts para Ollama/Gemini CLI.

---

## Fase B — Especificación funcional y técnica (documentos, sin código de app)

### Paso A4: Documento de requisitos + arquitectura
- `docs/ESPECIFICACION.md`: tickets digitales (QR cifrado + offline), fidelización (racha de viajes → boletos gratis/promos), telemetría GTFS-RT simulada→real, estados (retraso/corte de energía), animación 3D estilo Google Maps, PWA responsive, modelo IA local.
- Diagrama de componentes y flujo de datos.

---

## Fase C — MVP local (servidor del usuario + Ollama/Gemini CLI)

### Paso C1: Backend FastAPI + SQLite
- Endpoints: `/api/stops`, `/api/routes?from=&to=`, `/api/live/trains` (simulador de posición de trenes interpolada entre estaciones), `/api/alerts`, `/api/tickets/*`.
- Prueba: pytest + curl.

### Paso C2: Frontend PWA (MapLibre + three.js)
- Web + móvil con el mismo código (instalable en Android/iOS vía PWA; capa nativa con Capacitor opcional).
- Capa 3D: extrusión de líneas/túneles, trenes como modelos glTF animados con tween sobre la geometría de la ruta; cámara estilo Google Maps (pitch/rotate suave que sigue al tren).
- Túneles underground: atajos offline-first (Service Worker + IndexedDB cache del geojson y horarios) — *ver nota honesta sobre "WiFi gratis" abajo*.
- Prueba: Lighthouse PWA + apertura offline en modo avión simulado.

### Paso C3: Sistema de tickets + gamificación
- Billetera local: compra de boleto (mañana/noche, tarifa real ~Bs.S), QR dinámico rotativo (TOTP-like) escaneable por torniquete simulado.
- "Pasaporte Metro": viajes acumulados → niveles → boletos gratis, 2x1, promos de comercios aliados. Todo firmado HMAC en servidor para evitar fraude offline.
- Prueba: suite de unittest del motor de recompensas.

### Paso C4: Telemetría y estado de la red
- Simulador realista (headways L1 3–5 min, L2 4–7 min…) + formato **GTFS-RT protobuf** compatible para cuando exista feed oficial.
- Panel de incidencias: retrasos, cortes de energía, estaciones cerradas (fuente: redes sociales oficiales → scraper/manual al inicio).
- Prueba: animación 3D consume el feed simulado a 1 Hz sin saltos.

### Paso C5: IA local (Ollama / Gemini CLI)
- Modelos gratuitos recomendados: `llama3.2:3b` o `qwen2.5:3b` (Ollama, aptos para CPU/8 GB RAM) o Gemini API free-tier vía Gemini CLI.
- Asistente de viaje: RAG pequeño sobre `network.json` + alertas ("¿cómo llego de Gato Negro a Petare ahora?", "¿hay retrasos?"). El modelo NO inventa rutas: llama a las APIs del backend (function calling) y el backend responde con datos reales.
- Prueba: golden-set de 20 preguntas evaluadas.

### Paso C6: Empaque y despliegue
- Docker Compose (backend+frontend), script de backup del dataset, guía `docs/DESPLIEGUE.md`.

---

## ⚠️ Notas honestas (importante)

1. **"WiFi gratis en el vagón":** una app no puede dar WiFi donde no hay infraestructura. Lo que sí es viable:
   - Contenido 100% offline (mapa, horarios, rutas calculadas localmente en IndexedDB/WASM).
   - Enrutamiento *captive-portal friendly* si en el futuro SUVE/Metro instala APs en estaciones/vagones (la app actuaría como portal cliente ligero).
   - Posicionamiento subterráneo real: **no depende de internet**; se logra con beacon BLE/imán+acelerómetro (como hace CityMapper en Londres/NY) o Dead Reckoning con sensores del teléfono. La app muestra "última posición conocida + progreso estimado por túnel".
2. **Posición real de trenes:** hoy no existe GTFS-RT público del Metro de Caracas. Estrategia: empezar con simulación creíble basada en headways; luegoscraping de anuncios oficiales/app de Metro, o convenio con la institución. Dejar el pipeline GTFS-RT preparado.
3. **Tarifas/horarios** cambian frecuentemente en Venezuela: el dataset guarda `source` y fecha; el notebook incluye celda de re-fetch.

---

## Preguntas abiertas para ti (respóndelas cuando quieras, no bloquean los pasos ya hechos)
1. ¿Nombre definitivo de la app y paleta/branding? (uso "MetroVive" como placeholder)
2. ¿Stack preferido para tu servidor local: solo Python (FastAPI) o Node/TS? ¿RAM disponible para Ollama (≥8 GB?)
3. ¿El ticket debe parecerse a algo existente (p. ej. tarjeta Smart Card del metro) o 100% nuevo tipo QR?
4. ¿Quieres incluir desde el inicio el Metro de Los Teques, TRASEM (Mérida) y Metro de Valencia/Barquisimeto, o Fase 1 = solo Caracas + TRL?
5. ¿iOS también, o Android/web bastan para v1?
