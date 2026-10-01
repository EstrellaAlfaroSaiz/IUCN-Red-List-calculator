# IUCN Red List calculator

## EN:

IUCN Red List calculator is a QGIS plugin designed to support preliminary spatial workflows for IUCN Red List assessments, especially for plant occurrence datasets.

It downloads and filters GBIF occurrence records, combines them with user point layers, calculates Area of Occupancy (AOO) and Extent of Occurrence (EOO), and exports IUCN/SRedList-compatible Point Distribution outputs.

## ES:

IUCN Red List calculator es un complemento de QGIS diseñado para apoyar flujos de trabajo espaciales preliminares en evaluaciones de Lista Roja IUCN, especialmente con conjuntos de datos de presencia de plantas.

Descarga y filtra registros de presencia de GBIF, los combina con capas de puntos propias, calcula el Área de Ocupación (AOO) y la Extensión de Presencia (EOO), y exporta salidas Point Distribution compatibles con IUCN/SRedList.


## Recommended citation / Cita recomendada

Alfaro-Saiz, E. (2026). IUCN Red List calculator v1.2.0: QGIS plugin. Sociedad Española de Biología de la Conservación de Plantas (SEBiCoP).

## Scope / Alcance

EN: The outputs are intended to support expert review and do not replace a formal IUCN Red List assessment.

ES: Las salidas sirven como apoyo a la revisión experta y no sustituyen una evaluación formal de Lista Roja IUCN.


## AOO/EOO CRS note / Nota sobre CRS para AOO/EOO

EN: AOO and EOO are calculated in a projected CRS with metre units. GBIF and SRedList point outputs remain in WGS84 / EPSG:4326, but geographic CRS such as EPSG:4326 must not be used for the AOO grid because the grid cell size is expressed in metres. The main dropdown only lists projected CRS options; non-recommended display/geographic CRS can still be typed manually if needed, but geographic CRS are rejected for AOO/EOO calculation.

ES: AOO y EOO se calculan en un CRS proyectado con unidades en metros. Las salidas de puntos para GBIF y SRedList se mantienen en WGS84 / EPSG:4326, pero no debe usarse un CRS geográfico como EPSG:4326 para la cuadrícula AOO porque el tamaño de celda está expresado en metros. El desplegable principal solo muestra CRS proyectados; los CRS geográficos o de visualización no recomendados pueden escribirse manualmente si hiciera falta, pero los CRS geográficos se rechazan para el cálculo AOO/EOO.

## Version 1.1.0 / Versión 1.1.0

EN: Replaced 14 silent exception handlers in the user interface and spatial
processing helpers. Geometry errors during manual point deletion now halt
the deletion and report skipped features; failures to initialize export
feature fields or set existing manual-point attributes are reported explicitly.
Nonessential QGIS notification failures are recorded in the plugin log.

ES: Se han sustituido 14 manejadores de excepciones silenciosos en la
interfaz y en las funciones de procesamiento. Los errores geométricos
durante la eliminación de puntos detienen la operación e informan de los
registros afectados. Los fallos al preparar campos de exportación o
asignar atributos a puntos propios se comunican explícitamente.
Los fallos de notificaciones no esenciales se registran en el log.

### CSV import (v1.1.1)

Each imported CSV creates its own independent in-memory point layer, distinct from the layer of manually added points. The newly imported CSV (or shapefile) is the only layer checked for calculation initially; check other layers in tab 3 to intentionally combine datasets. CSV records with no inclusion or review value default to included/accepted, but explicit exclusion and review values remain effective. In-memory CSV layers should be exported to a persistent format before closing QGIS if they need to be retained.

### Version 1.2.0: input-selection safeguards / Control de capas de entrada

EN: Tab 3 now shows the explicitly selected calculation layers. Importing CSV,
shapefile/GeoPackage/GeoJSON, or downloading GBIF automatically selects only
the new layer, rather than silently selecting previously created manual/GBIF
layers. Press **Check active layer** or tick other layers to combine datasets.
Calculating with two or more checked layers now asks for confirmation without
silently changing the selection. The default AOO cell size remains the IUCN
2 × 2 km reference grid (2000 m); a reset button restores this size and a
nonstandard size requires confirmation. If no eligible points remain, the
error now lists each selected input layer and the exclusion reasons by layer.

ES: La pestaña 3 muestra las capas seleccionadas expresamente. Importar un CSV,
un archivo vectorial o descargar GBIF selecciona solo la nueva capa. Es posible
combinar capas marcándolas de forma explícita; si hay más de una, el cálculo
pide confirmación. El tamaño AOO inicial es 2000 m, dispone de un botón de
restablecimiento y exige confirmación si se modifica. Cuando no hay puntos
utilizables, se detallan las capas y los motivos de exclusión individualizados.

Note: an occupied 2 × 2 km cell contributes 4 km² to AOO; the cell-grid origin
can affect the occupied-cell count. Input CRS should use appropriate projected
metric coordinates; expert review is still essential for IUCN assessments.
