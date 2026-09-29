# IUCN Red List calculator

## EN:

IUCN Red List calculator is a QGIS plugin designed to support preliminary spatial workflows for IUCN Red List assessments, especially for plant occurrence datasets.

It downloads and filters GBIF occurrence records, combines them with user point layers, calculates Area of Occupancy (AOO) and Extent of Occurrence (EOO), and exports IUCN/SRedList-compatible Point Distribution outputs.

## ES:

IUCN Red List calculator es un complemento de QGIS diseñado para apoyar flujos de trabajo espaciales preliminares en evaluaciones de Lista Roja IUCN, especialmente con conjuntos de datos de presencia de plantas.

Descarga y filtra registros de presencia de GBIF, los combina con capas de puntos propias, calcula el Área de Ocupación (AOO) y la Extensión de Presencia (EOO), y exporta salidas Point Distribution compatibles con IUCN/SRedList.


## Recommended citation / Cita recomendada

Alfaro-Saiz, E. (2026). IUCN Red List calculator v1: QGIS plugin. Sociedad Española de Biología de la Conservación de Plantas (SEBiCoP).

## Scope / Alcance

EN: The outputs are intended to support expert review and do not replace a formal IUCN Red List assessment.

ES: Las salidas sirven como apoyo a la revisión experta y no sustituyen una evaluación formal de Lista Roja IUCN.


## AOO/EOO CRS note / Nota sobre CRS para AOO/EOO

EN: AOO and EOO are calculated in a projected CRS with metre units. GBIF and SRedList point outputs remain in WGS84 / EPSG:4326, but geographic CRS such as EPSG:4326 must not be used for the AOO grid because the grid cell size is expressed in metres. The main dropdown only lists projected CRS options; non-recommended display/geographic CRS can still be typed manually if needed, but geographic CRS are rejected for AOO/EOO calculation.

ES: AOO y EOO se calculan en un CRS proyectado con unidades en metros. Las salidas de puntos para GBIF y SRedList se mantienen en WGS84 / EPSG:4326, pero no debe usarse un CRS geográfico como EPSG:4326 para la cuadrícula AOO porque el tamaño de celda está expresado en metros. El desplegable principal solo muestra CRS proyectados; los CRS geográficos o de visualización no recomendados pueden escribirse manualmente si hiciera falta, pero los CRS geográficos se rechazan para el cálculo AOO/EOO.
