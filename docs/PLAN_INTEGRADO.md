# 🚇 MetroVive 3D — Plan Integrado v2 (Plan A + Plan B)

> Documento maestro. Fusiona el **Plan B** (pipeline técnico GTFS → FastAPI → MapLibre+Three.js → PWA → Docker → Ollama → lealtad/túnel, con pruebas por fase) y el **Plan A** (especificación arquitectónica completa: tabla de red ferroviaria, matriz de repos, SUVE/tarifas, IoT ESP32, portal cautivo, HCE/NFC, MetroPuntos).
> **Regla del proyecto:** cada paso termina con una prueba ejecutada `[OK]` antes del siguiente. Commit al final de cada paso.

---

## 0. Decisiones confirmadas (alcance vinculante)

| Decisión | Elección |
|---|---|
| Nombre | **MetroVive** (app) / **MetroVive 3D** (módulo de visualización) |
| Backend | **Python / FastAPI** + SQLite (GeoPandas/Shapely nativos, export directo desde notebook) |
| IA local | **Ollama + `llama3.2:3b`** (≥8 GB RAM, CPU-only OK; alternativa: Gemini CLI free-tier) |
| Ticket | **QR dinámico híbrido** (rota cada 60 s, cifrado AES-256-GCM offline) + billetera con identidad cromática SUVE: 🔴 Roja (público, orquídea), 🔵 Azul (estudiantes, turpial, −50 %), 🟡 Amarilla (adultos mayores/PcD, araguaney, gratis) |
| Alcance v1 | **Región Capital integrada**: Metro L1–L5, BusCaracas (L7), MetroCable, CableTren Bolivariano, Metro Los Teques (MLT), IFE Tuy Medio (La Rinconada ↔ Cúa). Valencia/Mérida → v2 |
| Plataformas | **PWA Web + Android** (React/Vite + vite-plugin-pwa; APK vía Capacitor) |

## 0.1 Correcciones honestas tras comparar ambos planes

1. **"WiFi gratis"**: la app no puede crear WiFi sin hardware. Se adopta la visión del Plan A como **Fase 6 opcional de hardware** (nodos ESP32-S3 con portal cautivo que sirve la PWA desde LittleFS), y en el MVP se usa la estrategia del Plan B: **offline-first + "Modo Túnel"** (dead-reckoning en el teléfono, telemetría sintética cuando no hay señal). El resto de funciones (mapa, rutas, QR) ya funcionan sin internet.
2. **Modelo IA**: Plan B decía `gemma:2b`; usaremos **`llama3.2:3b`** (confirmado). El modelo **no inventa rutas**: hace function-calling a los endpoints del backend (visión correcta del Plan A, punto 3).
3. **NFC/HCE**: se deja documentado (Plan A §5.1) pero **fuera del MVP** — requiere convenio real con SUVE. El QR dinámico local sí entra en v1 como *boleto validado internamente* (torniquete simulado); la validación real en torniquetes SUVE dependerá de API oficial (pregunta abierta §7).
4. **GTFS**: no existe feed oficial público. Estrategia combinada: dataset propio consolidado (`data/processed/network.json`, 56 paradas, grafo validado con Dijkstra) → **exportar a GTFS estático** (`shapes.txt` generado interpolando paradas donde falte geometría, tal como prevé el Plan B) → pipeline **GTFS-RT protobuf** preparado para el día que exista feed real o sensores propios.
5. **RuView/CSI (detección de trenes por estado del canal WiFi)**: fascinante pero investigación de frontera; va a Fase 7 experimental, no bloquea nada.

---

## 1. Estructura del repositorio (adoptada del Plan B, ampliada)

```text
metrovive/
├── docker-compose.yml
├── backend/
│   ├── Dockerfile
│   ├── requirements.txt
│   ├── app/
│   │   ├── main.py                 # FastAPI: /api/health, /api/stops, /api/routes,
│   │   │                           #  /api/trains/positions, /api/alerts, /api/chat,
│   │   │                           #  /api/tickets/*, /api/loyalty/*, /api/tunnel/*
│   │   ├── gtfs_loader.py          # Carga GTFS (timedelta >24:00 correcto)
│   │   ├── gtfs_export.py          # network.json -> GTFS estático (stops,trips,stop_times,shapes,calendar)
│   │   ├── position_engine.py      # Interpolación cinemática sobre shapes (Shapely)
│   │   ├── tunnel_mode.py          # Telemetría sintética (modo túnel / sin señal)
│   │   ├── loyalty.py              # MetroPuntos (Proof-of-Travel) + niveles + recompensas
│   │   ├── tickets.py              # QR dinámico AES-256-GCM, billetera SUVE-like (Roja/Azul/Amarilla)
│   │   ├── alerts.py               # Retrasos, cortes de energía, estaciones cerradas
│   │   └── ai_chat.py              # Router /api/chat -> Ollama (llama3.2:3b) + function calling
│   └── data/
│       ├── gtfs/                   # GTFS generado + raw
│       └── metro.db                # SQLite (usuarios, trips, puntos, boletos)
├── frontend/
│   ├── Dockerfile                  # build -> Nginx
│   ├── package.json
│   ├── vite.config.ts              # VitePWA (Workbox: NetworkFirst posiciones, precache shell)
│   ├── src/
│   │   ├── main.tsx / App.tsx
│   │   ├── components/
│   │   │   ├── Map3D.tsx           # MapLibre GL + @dvt3d/maplibre-three-plugin (pitch 60°)
│   │   │   ├── TrainLayer.tsx      # THREE.InstancedMesh (bloques MVP -> glTF Alstom Metropolis v2)
│   │   │   ├── ChatAssistant.tsx   # Asistente llama3.2:3b
│   │   │   ├── WalletPanel.tsx     # Billetera SUVE-like + QR 60s
│   │   │   └── LoyaltyPanel.tsx    # MetroPuntos, racha, canje de boletos gratis
│   │   └── lib/
│   │       ├── turfInterpolation.ts# turf.along/bearing para avance suave + orientación
│   │       └── api.ts              # Cliente REST + fallback caché offline
│   └── public/manifest.json        # "MetroVive", display standalone, iconos adaptativos
├── firmware/                       # FASE 6 opcional (ESP32 portal cautivo)
│   └── captive_portal.ino
├── notebook/MetroVive_Datos.ipynb  # Centro de datos: carga, validación, export GTFS, prompts IA
├── docs/ (PLAN_INTEGRADO.md, SKILLS.md, repos.md, ESPECIFICACION.md, DESPLIEGUE.md)
└── README.md
```

## 2. Matriz de repos (unificada — detalle y links en `docs/repos.md`)

| Repo/librería | Rol en MetroVive |
|---|---|
| `xuruata/venezuela-public-transportation` | Fuente primaria JSON/GeoJSON (ya descargada en `data/raw/`) |
| `Crom-Studio-C-A/transporte-publico-venezuela-gtfs` | GTFS base Metro Caracas; si faltan shapes → generar conectando paradas |
| `nagix/mini-tokyo-3d` | Arquitectura de referencia: animación espaciotemporal de metros (cámara sigue al tren estilo Google Maps) |
| `asdfghj1237890/mini-macau` | Pipeline polilíneas + instanciación masiva de mallas 3D |
| `maplibre/maplibre-gl-js` | Capa base vectorial, terreno, fill-extrusion |
| `mrdoob/three.js` | Render 3D WebGL (trenes, túneles extruidos) |
| `dvt3d/maplibre-three-plugin` | Puente MapLibre↔Three.js (sync de cámara/matrices) |
| `Turfjs/turf` | Interpolación `along`, `bearing`, snapping en el cliente |
| `googleapis/google-transit-data-feeds`, `gtfs-realtime-bindings` | Validador GTFS + protobuf GTFS-RT |
| `opentripplanner/OpenTripPlanner` | v2: motor de ruteo multimodal completo (nuestro Dijkstra cubre el MVP) |
| `ollama/ollama` (+ SDK python `ollama`) | IA local `llama3.2:3b` |
| `GoogleChromeLabs/pwa-workshop`, `vite-pwa-plugin` | PWA/Service Worker |
| `ionic/capacitor` | APK Android desde la misma PWA |
| `mathieucarbou/ESPAsyncWebServer`, `esphome ESPectre`, `ruvnet/RuView` | Fase 6/7: portal cautivo ESP32 y detección CSI (experimental) |

## 3. Red modelada en v1 (tabla consolidada A+B, coloreada según dataset)

| Subsistema | Ruta | Tipo | Paradas | Color UI |
|---|---|---|---|---|
| Metro L1 | Propatria ↔ Palo Verde | Subterránea/superficie | 22 | 🔴 #E30613 |
| Metro L2 | Las Adjuntas ↔ El Silencio | Subterránea/viaducto | 13 | 🟢 #009639 |
| Metro L3 | Plaza Venezuela ↔ La Rinconada | Subterránea | 9 | 🔵 #0072CE |
| Metro L4 | Capuchinos ↔ Zona Rental | Subterránea | 5 | 🟡 #FFCD00 |
| Metro L5 | Zona Rental ↔ Bello Monte | (fase parcial) | 1 op. | 🟣 |
| MLT (Los Teques) | Las Adjuntas ↔ Independencia | Ferroviaria/viaducto | 4 | Marrón |
| IFE Tuy Medio | Caracas (Libertador) ↔ Cúa | Superficie/túneles | 4 | Gris ferro |
| CableTren | Petare II ↔ Warairarepano | Guiado elevado | 5 | Naranja |
| MetroCable | San Agustín / Mariche / La Dolorita | Teleférico | varios | Celeste |
| BusCaracas L7 | Las Flores ↔ Los Ilustres | BRT | 11 | Verde bus |

Nodos intermodales clave (ya detectados automáticamente en `network.json`): **La Rinconada ↔ Caracas Libertador (92 m)**, **Las Adjuntas ↔ MLT**, **Plaza Venezuela ↔ Zona Rental (L1/L3/L4)**, Bellas Artes ↔ Parque Central (MetroCable, 304 m).

## 4. Tarifas SUVE (base del módulo de tickets)

| Tarjeta | Símbolo | Público | Tarifa (referencia 2025, verificar vigente) |
|---|---|---|---|
| Roja | Orquídea | Público general | Plena (Bs. ~5,00 metro/metrobús; ~10,00 IFE) |
| Azul | Turpial | Estudiantes | −50 % (requiere constancia de estudio) |
| Amarilla | Araguaney | Adultos mayores / PcD | Gratis (exoneración 100 %) |

---

## 5. Plan de ejecución por fases (cada paso con prueba)

### ✅ Fase 1 — Datos y notebook (completada, se re-valida)
- Dataset consolidado: 56 paradas / 4 sistemas / 58 aristas + transbordos; Dijkstra probado.
- **Paso 1.1** Notebook `MetroVive_Datos.ipynb`: carga, mapa interactivo, validaciones, export GTFS, prompts Ollama. *(prueba: ejecutar nbconvert sin errores)*
- **Paso 1.2** Export GTFS estático (`gtfs_export.py`): stops/trips/stop_times/shapes/calendar; shapes generados interpolando paradas donde no hay geometría. *(prueba: validar con `gtfs-realtime-bindings`/validador + contar filas)*

### Fase 2 — Backend: motor de posiciones (Plan B F1)
- **2.1** `gtfs_loader.py` (tiempos como `Timedelta`, viajes >24:00). *(prueba: unit test parsea 24:20:00)*
- **2.2** `position_engine.py`: segmentos precalculados (d0,d1 acumulados por shape) + `positions_at(t)` vectorizado con Shapely. *(prueba: t=08:00 devuelve puntos ON la Línea 1)*
- **2.3** FastAPI: `/api/health`, `/api/trains/positions?t=HH:MM:SS`, `/api/stops`, `/api/routes?from=&to=` (Dijkstra del notebook portado). *(prueba: curl + pytest; coordenadas caen sobre las líneas)*

### Fase 3 — Frontend 3D (Plan B F2 + Mini Tokyo style)
- **3.1** MapLibre (estilo oscuro, pitch 60°) + plugin Three.js. *(prueba: mapa renderiza Caracas)*
- **3.2** `TrainLayer` con **InstancedMesh** (60 trenes objetivo ≥55 FPS móvil, criterio Plan A) + interpolación turf + `requestAnimationFrame`; bearing para orientar. *(prueba: bloque mueviéndose continuo L1 Propatria↔Palo Verde, velocidad = headway GTFS)*
- **3.3** Cámara "sigue-al-tren" estilo Google Maps (flyTo + easing). *(prueba manual grabada)*

### Fase 4 — PWA + offline (Plan B F3)
- **4.1** vite-plugin-pwa: precache shell, runtime `NetworkFirst` para `/api/trains/positions` (maxAge 60 s), IndexedDB para última posición + geojson. *(prueba: DevTools SW activo; modo avión abre la app con última posición)*
- **4.2** Manifest MetroVive + íconos; Lighthouse PWA ≥90. *(prueba: auditoría)*

### Fase 5 — Docker + IA (Plan B F4/F5 corregido)
- **5.1** `docker-compose.yml`: backend(8000)+frontend(80 nginx)+ollama(11434), volúmenes persistentes (metro.db, modelos). *(prueba: up --build; reinicio conserva datos)*
- **5.2** `/api/chat` con `ollama.Client(host="http://ollama:11434")`, modelo `llama3.2:3b`, **function calling** al backend (rutas reales, sin alucinación). *(prueba: "¿Cómo llego de Capitolio a Zona Rental?" → responde Línea 4 directa; golden-set 20 preguntas)*

### Fase 6 — Tickets + lealtad + modo túnel (Plan B F6 + Plan A §5)
- **6.1** Billetera SUVE-like: perfiles Roja/Azul/Amarilla, saldo local cifrado, **QR dinámico AES-256-GCM que rota cada 60 s** (offline, HMAC timestamp, rechazo >60 s). Torniquete simulado en `/api/tickets/validate`. *(prueba: generar QR sin red, validarlo, y que un QR viejo sea rechazado)*
- **6.2** MetroPuntos Proof-of-Travel: `puntos = km × factor_modo × mult_usuario` (bonificación a modos intermodales IFE/MetroCable/CableTren); niveles → boletos gratis/cupones. Tablas `users`, `trips`, `rewards` en SQLite. *(prueba: suite unittest del motor de recompensas)*
- **6.3** Modo Túnel: `POST /api/tunnel/start` → tramas sintéticas 2 s con jitter realista usando el mismo motor; en el cliente, dead-reckoning por acelerómetro/GPS último + horario. *(prueba: modo avión, el tren sigue avanzando suave y muestra ETA)*
- **6.4** Alertas: `/api/alerts` (retrasos/cortes de energía/estación cerrada) formato `ServiceAlert` GTFS-RT; entrada manual al inicio. *(prueba: alerta inyectada pinta el tramo rojo en 3D)*

### Fase 7 — Extras diferidos (roadmap, no MVP)
- Firmware ESP32 portal cautivo sirviendo la PWA desde LittleFS (Plan A §4) — requiere autorización del Metro (ver §7).
- NFC HCE ISO/IEC 14443 — requiere convenio SUVE.
- Sensores RSSI/CSI (ESPectre/RuView) para posición real de trenes.
- GTFS-RT protobuf real cuando exista fuente.
- Metro Valencia, TRASEM Mérida, Barquisimeto (v2).

---

## 6. Resumen de pruebas por fase

| Fase | Acción | Criterio de aceptación |
|---|---|---|
| 1 | `jupyter nbconvert --execute` + export GTFS | 0 errores; GTFS validado; ≥56 paradas |
| 2 | `curl :8000/api/trains/positions?t=08:00:00` | Coordenadas sobre las líneas |
| 3 | Abrir frontend | Tren 3D continuo en L1; InstancedMesh; FPS estable |
| 4 | Build + modo avión | App abre, muestra última posición cacheada |
| 5 | `docker compose up` + POST /api/chat | 3 servicios vivos, persisten; ruta coherente (L4 directa) |
| 6 | QR offline + torniquete simulado + túnel | QR válido <60 s, inválido después; puntos acreditados; tren avanza sin red |

## 7. Preguntas abiertas (a operadores/instituciones — no bloquean el desarrollo)
1. ¿Existe API/SDK público de SUVE (portal.suve.com.ve) para sincronizar saldo/recarga, o la app opera con saldo local cifrado? *(por ahora: local)*
2. ¿Permiten montar nodos ESP32 en gargantas de andén/túneles? ¿Hay energía 12/24 V DC en cabinas?
3. ¿Tablas horarias electrónicas oficiales o hay que tomar tiempos en campo? *(por ahora: headways estimados L1 3–5 min, L2 4–7 min…)*
4. Tarifas vigentes exactas (cambian con frecuencia) — el dataset guarda `source` y fecha; celda de re-fetch en el notebook.
