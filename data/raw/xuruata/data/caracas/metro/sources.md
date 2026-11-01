# Sources — Metro de Caracas

## Lines, station ordering, official line names
- [Wikipedia EN — Caracas Metro](https://en.wikipedia.org/wiki/Caracas_Metro)
- [Wikipedia EN — List of Caracas Metro stations](https://en.wikipedia.org/wiki/List_of_Caracas_Metro_stations)
- [Wikipedia ES — Metro de Caracas](https://es.wikipedia.org/wiki/Metro_de_Caracas)
- [Wikipedia ES — Línea 1 (Metro de Caracas)](https://es.wikipedia.org/wiki/L%C3%ADnea_1_(Metro_de_Caracas))
- [Wikipedia ES — Línea 3 (Metro de Caracas)](https://es.wikipedia.org/wiki/L%C3%ADnea_3_(Metro_de_Caracas))

## Station coordinates
Pulled from Wikidata via SPARQL on 2026-05-25. The `wikidata` field on each stop
contains the Wikidata QID — useful for re-pulling future updates. See
`raw/wikidata_stations.json` for the dump.

## Operational status
- Lines 1, 2, 3, 4 are operational (47 unique stations).
- Line 3's published extension toward El Silencio (Prado de María, El Peaje, San Agustín,
  Fuerzas Armadas, Urdaneta, San José) is marked `under_construction`.
- Line 4's eastward extension (Bello Monte through Miranda II) is marked `under_construction`.
- Line 5 (Las Mercedes / Baruta / El Hatillo corridor) is marked `under_construction`.
- Line 6 (Los Magallanes / La Urbina corridor) is marked `planned`.

## Caveats
- A few "L4" coordinates (Bello Campo, Chuao, Miranda II) come from the planning
  Wikidata records and may be approximate to ±100 m.
- Line and stop colors follow conventions used by Wikipedia's network diagrams; the
  agency does not publish a normative color palette.
