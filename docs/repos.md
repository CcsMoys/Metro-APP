# 📦 Repos GitHub investigados — insumos para MetroVive

## A. Datos abiertos del transporte venezolano (Fuentes primarias)
| Repo | Qué aporta | Estado |
|---|---|---|
| [xuruata/venezuela-public-transportation](https://github.com/xuruata/venezuela-public-transportation) | **JSON canónico + GeoJSON + GTFS de 10 sistemas**: Metro Caracas (47 est.), Tren Libertador/SUVE, Metrocable San Agustín, Teleférico Ávila, Metrobús, Transbarca… Con colores oficiales, `stops_ordered`, wikidata y CI que reconstruye los feeds. Liccha ODbL. | ✅ Descargado en `data/raw/xuruata/` |
| [Crom-Studio-C-A/transporte-publico-venezuela-gtfs](https://github.com/Crom-Studio-C-A/transporte-publico-venezuela-gtfs) | GTFS completo del Metro de Caracas: `stops.txt`, `trips.txt`, `stop_times.txt`, `shapes.txt` (geometrías finas de vía, ¡útil para el 3D!), `frequencies.txt`, tarifas y hasta noticias. Web demo en GH Pages. | 📋 Clonar cuando armemos shapes 3D |
| [OpenTransitTools/feed](https://github.com/OpenTransitTools/feed) | Padrón mundial de sistemas de transporte (ID VE-M000008 = Metro Caracas). Útil para metadata/normalización. | Referencia |
| Wikidata/Wikipedia (Q208054 etc.) | Coordenadas y fechas de cada estación; L4 extendida a "Caracas" (conexión con TRL, 2025). | Validado cruzado |

## B. Motores de ruteo / estándar GTFS
| Herramienta | Uso en el proyecto |
|---|---|
| [GTFS spec](https://gtfs.org/reference/static) + [GTFS-Realtime](https://gtfs.org/reference/realtime) | Formato de nuestros datos estáticos y del feed de posición de trenes/retrasos/cancelaciones. |
| [google/gtfs-realtime-bindings](https://github.com/google/gtfs-realtime-bindings) | Protobuf oficial (Python/JS) para simular y consumir GTFS-RT. |
| [opentripplanner/OpenTripPlanner](https://github.com/opentripplanner/OpenTripPlanner) | Motor profesional multimodal (camine+bici+transbordo). Fase 2: reemplaza a nuestro Dijkstra casero. Requiere Java, corre bien en servidor local. |
| [Bkly/leprechaun](https://github.com/Bkly/leprechaun), [tylerjbrophy/simple-gtfs-example](https://github.com/tylerjbrophy/simple-gtfs-example) | Referencias para generar GTFS propio desde cero. |
| [ MobilityData/gtfs-validator](https://github.com/MobilityData/gtfs-validator) | Validar que nuestro GTFS sea correcto antes de publicar. |

## C. Mapas 2D/3D y animación (el "estilo Google Maps")
| Librería | Por qué |
|---|---|
| [maplibre/maplibre-gl-js](https://github.com/maplibre/maplibre-gl-js) | Mapa vectorial gratis (fork de Mapbox GL sin costo), funciona en web y Android/iOS (maplibre-native). Soporta `pitch`, extrusión 3D, capas GeoJSON, estilo oscuro. **Base recomendada.** |
| [mrdoob/three.js](https://github.com/mrdoob/three.js) + [TWEEN](https://github.com/tweenjs/tween.js) | Capa 3D custom sobre el mapa (modelo glTF de tren, interpolación suave por la ruta, túneles). Ver ejemplo oficial `webgl_loader_maplibre` / overlays MapLibre+three. |
| [CesiumGS/cesium](https://github.com/CesiumGS/cesium) | Alternativa globe 3D completo (globo terráqueo, tiempo real). Más pesado; opcional para vista "pájaro 3D". |
| [MapLibre examples: GPS location & geolocation](https://maplibre.org/maplibre-gl-js/docs/examples/) | Recetas: seguir posición, rutas animadas (`trailDashArray`), modelo 3D moviéndose (ej. "Add a 3D model"). |
| [osmdroid/osmdroid](https://github.com/osmdroid/osmdroid) o [maplibre-native-Android](https://github.com/maplibre/maplibre-native) | Si luego hacemos app nativa Android además de PWA. |
| Tiles gratis: OpenFreeMap, MapTiler free, VersaTiles (sin API key) | Fondo de mapa para Caracas sin costo ni llaves. |

## D. Apps similares (inspiración funcional, incluye Vía Libre)
| Proyecto | Qué copiarle |
|---|---|
| **Vía Libre** (vialibre.soft-flow.app) | UX venezolana: búsqueda origen→destino, lista de paradas, combinación de sistemas. |
| [Theory-Bus-Ltd/transit-app](https://github.com/Theory-Bus-Ltd/transit-app) / [Transit App](https://transitapp.com) | Referente mundial de tiempos de espera + alertas de servicio. |
| [CityMapper blog: subway tracking](https://medium.com/city-mapper/mapping-nyc-subway-cellular-offline-8d43f046f95) | Cómo posicionarse bajo tierra sin GPS (beacons BLE, histéresis celular). |
| [AFTN/metro-transit-apps: open-metro](https://github.com/aftn) y [public-transport repo list](https://github.com/public-transport) | Ecosistema completo GTFS. |
| [YosefKoon/Transportr alternatives] / [OsmAnd](https://github.com/osmandapp/OsmAnd) | Navegación offline total (descarga de mapas al WiFi de casa). |
| Ticketing: [OpenSource ticket apps — e.g. pretix](https://github.com/pretix/pretix) | Arquitectura de tickets QR rotativos + validación offline (nosotros haremos versión ligera). |
| Gamificación: patrones de Foursquare/SwissPass "travel pass" | Rachas, niveles, canje por boletos gratis. |

## E. IA local (gratis)
| Herramienta | Detalle |
|---|---|
| [ollama/ollama](https://github.com/ollama/ollama) | Corre `llama3.2:3b`, `qwen2.5:3b`, `phi3:mini` en CPU/8GB. API HTTP local `localhost:11434`. |
| [google-gemini/gemini-cli](https://github.com/google-gemini/gemini-cli) | CLI gratuito con Gemini (free-tier); útil para generar código del proyecto en el servidor local. |
| [langchain-ai/langchain](https://github.com/langchain-ai/langchain) / [ollama-python](https://github.com/ollama/ollama-python) | RAG + function calling contra nuestras APIs. |

## F. Offline-first / PWA
| Librería | Uso |
|---|---|
| Workbox ([GoogleChrome/workbox](https://github.com/GoogleChrome/workbox)) | Service Worker: cache de tiles, geojson, rutas calculadas. |
| [Ionic capacitor](https://github.com/ionic-team/capacitor) | Empaquetar la PWA como APK/AAB real para Play Store si se requiere. |
| LocalStorage → [Dexie.js](https://github.com/dexie/Dexie.js) (IndexedDB) | Billetera de tickets y pasaporte de viajes offline. |
