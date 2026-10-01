# Changelog

## 1.2.0 (2026-10-01)

- Tab 3 displays an explicit summary of input layers; refreshing the list preserves user-selected layers without silently enabling other project layers.
- New GBIF downloads, CSV imports and vector-file imports select only their new layer. Manual points no longer silently get added to an existing calculation selection.
- When multiple input layers are checked, the user must confirm intentional combination before calculating; cancelled calculations do not alter selections.
- Default AOO grid remains 2000 m (IUCN 2 × 2 km reference); a reset button and confirmation for nonstandard cell sizes prevent accidental 1992 m calculations.
- Empty-result errors report selected layers and exclusions broken down by source layer with instructions to verify the selection and include/review status.
- Python syntax and isolated selection/diagnostic checks were carried out. Interactive QGIS validation is still required prior to publication.


## 1.1.1 (2026-10-01)

- CSV imports now produce independent layers rather than adding records to the manual-points layer. Each import preserves its source path and selects only the newly imported layer for calculation.
- A CSV without explicit include/review values defaults to included/accepted; explicit false/rejected/review settings are retained. Manual-entry defaults remain unchanged.
- Shapefile import also selects the newly imported layer alone to avoid accidental mixing; other layers can be added using tab 3.
- Deduplication now runs after eligibility filters so excluded points cannot consume the coordinate of an eligible observation.
- Added coordinate-header validation and rejected out-of-range WGS84 CSV coordinates.


## 1.1.0 (2026-10-01)

- Removed the 14 broad silent `except Exception: pass` / `continue` handlers reported in `dialog.py` and `processing_logic.py`.
- UI initialization issues now fail visibly instead of leaving controls partly configured.
- Geometry or spatial-query errors stop manual point deletion and identify skipped features in the plugin log.
- Layer-import validation errors stop the import, whereas nonessential QGIS UI notifications are recorded in the plugin log without undoing successful operations.
- Failed assignments to existing user-point fields and output feature-field initialization now raise informative errors.
- Updated metadata version and recommended citation to 1.1.

Validation: Python syntax, static exception-handler checks, package integrity, and isolated helper smoke tests. Full QGIS 3/4 interactive integration tests must be completed in QGIS before publication.
