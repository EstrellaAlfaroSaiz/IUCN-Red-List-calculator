# -*- coding: utf-8 -*-
"""Core spatial logic for AOO/EOO calculations."""

from __future__ import annotations

import csv
import json
import math
import os
import tempfile
from datetime import datetime

try:
    from qgis.PyQt.QtCore import QVariant
except ImportError:  # pragma: no cover - defensive Qt6 fallback
    class QVariant:  # minimal type aliases accepted by QgsField in many bindings
        String = str
        Int = int
        Double = float
        Bool = bool

from qgis.core import (
    QgsCoordinateReferenceSystem,
    QgsCoordinateTransform,
    QgsFeature,
    QgsField,
    QgsFields,
    QgsGeometry,
    QgsPointXY,
    QgsProject,
    QgsVectorLayer,
    QgsVectorFileWriter,
    QgsCoordinateTransformContext,
    QgsWkbTypes,
    Qgis,
)


def _is_point_layer(layer) -> bool:
    """Return True for point vector layers across QGIS 3 and QGIS 4 APIs.

    QGIS 4 changed several enum names. This function is deliberately
    permissive, because the real geometry of each feature is checked again
    in collect_usable_points().
    """
    if not _valid_layer(layer):
        return False
    try:
        wkb = layer.wkbType()
        geom_type = QgsWkbTypes.geometryType(wkb)
        if str(geom_type).lower().find("point") >= 0:
            return True
        if str(wkb).lower().find("point") >= 0:
            return True
    except Exception:
        pass
    try:
        geom_type = layer.geometryType()
        if str(geom_type).lower().find("point") >= 0:
            return True
        candidates = []
        if hasattr(QgsWkbTypes, "PointGeometry"):
            candidates.append(QgsWkbTypes.PointGeometry)
        if hasattr(Qgis, "GeometryType") and hasattr(Qgis.GeometryType, "Point"):
            candidates.append(Qgis.GeometryType.Point)
        return geom_type in candidates
    except Exception:
        return True


GBIF_FIELD_SPECS = [
    ("gbifID", QVariant.String),
    ("scientificName", QVariant.String),
    ("taxonKey", QVariant.String),
    ("basisOfRecord", QVariant.String),
    ("occStatus", QVariant.String),
    ("estMeans", QVariant.String),
    ("eventDate", QVariant.String),
    ("year", QVariant.Int),
    ("countryCode", QVariant.String),
    ("datasetKey", QVariant.String),
    ("institution", QVariant.String),
    ("collection", QVariant.String),
    ("recordedBy", QVariant.String),
    ("identifiedBy", QVariant.String),
    ("coordUncM", QVariant.Double),
    ("issues", QVariant.String),
    ("data_origin", QVariant.String),
    ("review", QVariant.String),
    ("include", QVariant.Bool),
]

MANUAL_FIELD_SPECS = [
    ("scientificName", QVariant.String),
    ("eventDate", QVariant.String),
    ("data_citation", QVariant.String),
    ("observer", QVariant.String),  # retained for compatibility with older projects
    ("source_ref", QVariant.String),
    ("data_origin", QVariant.String),
    ("data_curator", QVariant.String),
    ("evidence", QVariant.String),
    ("identifier", QVariant.String),
    ("catalog_no", QVariant.String),
    ("coordUncM", QVariant.Double),
    ("review", QVariant.String),
    ("include", QVariant.Bool),
    ("notes", QVariant.String),
]

USED_POINT_FIELD_SPECS = [
    ("scientificName", QVariant.String),
    ("data_origin", QVariant.String),
    ("source_ref", QVariant.String),
    ("gbifID", QVariant.String),
    ("datasetKey", QVariant.String),
    ("review", QVariant.String),
    ("coordUncM", QVariant.Double),
]

REPORT_FIELD_SPECS = [
    ("seccion", QVariant.String),
    ("campo", QVariant.String),
    ("valor", QVariant.String),
]

DATASET_COUNTS_FIELD_SPECS = [
    ("datasetKey", QVariant.String),
    ("count", QVariant.Int),
]

EXCLUDED_FIELD_SPECS = [
    ("source_layer", QVariant.String),
    ("feature_id", QVariant.String),
    ("reason", QVariant.String),
]

# Exact schema supplied by the user for the CSV Point Distribution file.
# Do not add fields here unless the template changes.
POINT_DISTRIBUTION_FIELDS = [
    "sci_name", "presence", "origin", "seasonal", "compiler", "yrcompiled",
    "citation", "dec_lat", "dec_long", "spatialref", "subspecies", "subpop",
    "data_sens", "sens_comm", "event_year", "source", "basisofrec",
    "catalog_no", "dist_comm", "island", "tax_comm",
]

_POINT_DISTRIBUTION_INT_FIELDS = {"presence", "origin", "seasonal", "yrcompiled", "data_sens", "event_year"}
_POINT_DISTRIBUTION_DOUBLE_FIELDS = {"dec_lat", "dec_long"}

POINT_DISTRIBUTION_FIELD_SPECS = []
for _field_name in POINT_DISTRIBUTION_FIELDS:
    if _field_name in _POINT_DISTRIBUTION_INT_FIELDS:
        POINT_DISTRIBUTION_FIELD_SPECS.append((_field_name, QVariant.Int))
    elif _field_name in _POINT_DISTRIBUTION_DOUBLE_FIELDS:
        POINT_DISTRIBUTION_FIELD_SPECS.append((_field_name, QVariant.Double))
    else:
        POINT_DISTRIBUTION_FIELD_SPECS.append((_field_name, QVariant.String))

# IUCN Standard attributes for spatial distribution layers.
# These are applied to the AOO and EOO polygon layers, not to the Point Distribution CSV.
IUCN_POLYGON_FIELD_SPECS = [
    # Campos obligatorios o condicionales para capas espaciales IUCN AOO/EOO.
    # Se eliminan los campos solo recomendados/opcionales de la interfaz y de las capas.
    ("sci_name", QVariant.String),
    ("presence", QVariant.Int),
    ("origin", QVariant.Int),
    ("seasonal", QVariant.Int),
    ("compiler", QVariant.String),
    ("yrcompiled", QVariant.Int),
    ("citation", QVariant.String),
    ("subspecies", QVariant.String),
    ("data_sens", QVariant.Int),
    ("sens_comm", QVariant.String),
    ("generalisd", QVariant.Int),
]

IUCN_POLYGON_FIELD_GUIDE = [
    ("sci_name", "Scientific name of the taxon; it must match SIS.", "Required"),
    ("presence", "IUCN code for the taxon presence in the area.", "Required"),
    ("origin", "IUCN code for the origin of presence in the area.", "Required"),
    ("seasonal", "IUCN code for seasonal presence.", "Required if applicable"),
    ("compiler", "Person or institution responsible for generating the layer.", "Required"),
    ("yrcompiled", "Year when the layer is compiled or modified.", "Required"),
    ("citation", "Overall credit for the map data for IUCN; it should be the same throughout the file.", "Required"),
    ("subspecies", "Infraspecific epithet if a subspecies or variety is assessed.", "Required if applicable"),
    ("data_sens", "Indicates whether the layer shows sensitive data: 0 = no, 1 = yes.", "Required if sensitive"),
    ("sens_comm", "Reason why the distribution is sensitive.", "Required if data_sens=1"),
    ("generalisd", "Indicates whether the polygon is generalized: AOO=0 and EOO=1 automatically.", "Required if generalized"),
]

IUCN_FIELD_GUIDE_SPECS = [
    ("field", QVariant.String),
    ("definition", QVariant.String),
    ("requirement", QVariant.String),
]

# Retained only for backwards compatibility inside this module; the plugin no longer
# creates a separate Point Distribution help table.
IUCN_POINT_FIELD_GUIDE_SPECS = IUCN_FIELD_GUIDE_SPECS

IUCN_POINT_FIELD_GUIDE = [
    ("sci_name", "Scientific name of the taxon.", "Required", "Text(100)", "E.g.: Sideritis lurida; include infraspecific rank if applicable."),
    ("presence", "IUCN code for presence at the point.", "Required", "Short Integer", "Allowed values for points: 1, 3, 4, 5, 6. For AOO/EOO, normally use 1 = Extant."),
    ("origin", "IUCN code for the origin of presence.", "Required", "Short Integer", "1 Native, 2 Reintroduced, 3 Introduced, 4 Vagrant, 5 Origin Uncertain, 6 Assisted Colonisation."),
    ("seasonal", "IUCN code for seasonal presence.", "Required if applicable", "Short Integer", "Default is 1 Resident if not applicable or not specified."),
    ("compiler", "Person or institution compiling the points.", "Required", "Text(254)", "Blank by default; fill only if you want to assign one common compiler to all points."),
    ("yrcompiled", "Year the points were compiled or modified.", "Required", "Short Integer", "Current year by default."),
    ("citation", "Overall credit for the map/distribution data for the assessment.", "Required", "Text(254)", "It should be the same throughout the file."),
    ("dec_lat", "Latitud decimal en el sistema indicado en spatialref.", "Required", "Float", "Entre -90 y 90; el plugin exporta WGS84."),
    ("dec_long", "Longitud decimal en el sistema indicado en spatialref.", "Required", "Float", "Entre -180 y 180; el plugin exporta WGS84."),
    ("spatialref", "Coordinate reference system.", "Required", "Text(100)", "Preferred: WGS84 / EPSG:4326."),
    ("subspecies", "Subspecies or variety epithet, if applicable.", "Required if applicable", "Text(100)", "It must match SIS if an infraspecific taxon is being assessed."),
    ("subpop", "Subpopulation name, if applicable.", "Required if applicable", "Text(100)", "E.g.: subpopulation X."),
    ("data_sens", "Indica si la localidad es sensible.", "Required if sensitive", "Boolean 0/1", "0 por defecto; si es 1 debe completarse sens_comm."),
    ("sens_comm", "Reason why the data are sensitive.", "Required if data_sens=1", "Text(254)", "Do not include details that unnecessarily reveal sensitive localities."),
    ("event_year", "Year of observation or collection event.", "Recommended", "Short Integer", "Filled from year/eventDate when available."),
    ("source", "Primary source of the points.", "Recommended", "Text(254)", "E.g.: GBIF.org, fieldwork, herbarium, publication."),
    ("basisofrec", "Nature of the record according to Darwin Core.", "Recommended", "Text(30)", "E.g.: PreservedSpecimen, HumanObservation, MachineObservation."),
    ("catalog_no", "Identificador del registro o material.", "Recommended", "Text(254)", "En GBIF se rellena con gbifID cuando procede."),
    ("dist_comm", "Distribution comments associated with the point.", "Recommended", "Text(254)", "Type locality, protected area, precision, etc."),
    ("island", "Isla si es relevante.", "Recommended if applicable", "Text(150)", "Solo si procede."),
    ("tax_comm", "Taxonomic comments for the point.", "Recommended", "Text(254)", "Notes on identification, subspecies or subpopulation."),
]


def _safe_float(value, default=None):
    if value in (None, ""):
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _safe_int(value, default=None):
    if value in (None, ""):
        return default
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return default


def _to_bool(value) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return False
    return str(value).strip().lower() in {"true", "1", "yes", "sí", "si", "accepted", "aceptado"}


def _year_from_event_date(value):
    text = "" if value is None else str(value).strip()
    if len(text) >= 4 and text[:4].isdigit():
        return text[:4]
    return ""



def _truncate(value, max_len=None):
    text = "" if value is None else str(value)
    if max_len is not None and len(text) > max_len:
        return text[:max_len]
    return text


def _int_or_blank(value):
    if value in (None, ""):
        return ""
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return ""

def _value_for_qgis_field(field, value):
    """Convert blank optional values to NULL for numeric vector fields.

    Shapefile export fails if an integer/double field receives an empty
    string. CSV can keep blanks, but vector layers need None/NULL for
    missing numeric attributes such as event_year.
    """
    try:
        field_type = field.type()
    except Exception:
        field_type = None

    text_blank = value is None or value == ""
    int_types = {getattr(QVariant, name, None) for name in ("Int", "LongLong", "UInt", "ULongLong")}
    double_types = {getattr(QVariant, name, None) for name in ("Double",)}

    if field_type in int_types:
        if text_blank:
            return None
        try:
            return int(float(value))
        except (TypeError, ValueError):
            return None
    if field_type in double_types:
        if text_blank:
            return None
        try:
            return float(value)
        except (TypeError, ValueError):
            return None
    return "" if value is None else value


def _int_or_null(value):
    """Return an int or NULL/None for numeric fields in vector layers.

    QGIS 4 memory layers can reject a feature silently when an integer or
    double field receives an empty string. For optional numeric IUCN fields
    such as id_no or hybas_id, use NULL instead of "".
    """
    if value in (None, ""):
        return None
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return None


def _float_or_null(value):
    if value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _basis_to_iucn(value):
    """Convert GBIF vocabulary values to IUCN/Darwin Core BasisOfRecord examples."""
    text = "" if value is None else str(value).strip()
    allowed = {
        "PreservedSpecimen", "FossilSpecimen", "LivingSpecimen",
        "HumanObservation", "MachineObservation", "StillImage",
        "MovingImage", "SoundRecording"
    }
    mapping = {
        "HUMAN_OBSERVATION": "HumanObservation",
        "MACHINE_OBSERVATION": "MachineObservation",
        "PRESERVED_SPECIMEN": "PreservedSpecimen",
        "FOSSIL_SPECIMEN": "FossilSpecimen",
        "LIVING_SPECIMEN": "LivingSpecimen",
        "OBSERVATION": "HumanObservation",
        "pliego/testigo": "PreservedSpecimen",
        "field observation": "HumanObservation",
        "photograph": "StillImage",
        "informe": "HumanObservation",
        "bibliography": "HumanObservation",
    }
    converted = mapping.get(text, mapping.get(text.upper(), text))
    return converted if converted in allowed else ""


def _valid_layer(layer) -> bool:
    if layer is None:
        return False
    try:
        return layer.isValid()
    except RuntimeError:
        return False


def make_fields(specs):
    fields = QgsFields()
    for name, variant in specs:
        fields.append(QgsField(name, variant))
    return fields


def create_occurrence_layer(records, layer_name: str = "GBIF occurrences filtered") -> QgsVectorLayer:
    layer = QgsVectorLayer("Point?crs=EPSG:4326", layer_name, "memory")
    provider = layer.dataProvider()
    provider.addAttributes([QgsField(name, typ) for name, typ in GBIF_FIELD_SPECS])
    layer.updateFields()

    features = []
    for rec in records:
        lat = _safe_float(rec.get("decimalLatitude"))
        lon = _safe_float(rec.get("decimalLongitude"))
        if lat is None or lon is None:
            continue
        if not (-90 <= lat <= 90 and -180 <= lon <= 180):
            continue
        if abs(lat) < 1e-12 and abs(lon) < 1e-12:
            continue

        feat = QgsFeature(layer.fields())
        feat.setGeometry(QgsGeometry.fromPointXY(QgsPointXY(lon, lat)))
        feat["gbifID"] = str(rec.get("gbifID", ""))
        feat["scientificName"] = rec.get("scientificName", "")
        feat["taxonKey"] = str(rec.get("taxonKey", ""))
        feat["basisOfRecord"] = rec.get("basisOfRecord", "")
        feat["occStatus"] = rec.get("occurrenceStatus", "")
        feat["estMeans"] = rec.get("establishmentMeans", "")
        feat["eventDate"] = rec.get("eventDate", "")
        feat["year"] = _safe_int(rec.get("year"))
        feat["countryCode"] = rec.get("countryCode", "")
        feat["datasetKey"] = rec.get("datasetKey", "")
        feat["institution"] = rec.get("institutionCode", "")
        feat["collection"] = rec.get("collectionCode", "")
        feat["recordedBy"] = str(rec.get("recordedBy", ""))
        feat["identifiedBy"] = str(rec.get("identifiedBy", ""))
        feat["coordUncM"] = _safe_float(rec.get("coordinateUncertaintyInMeters"))
        feat["issues"] = rec.get("issues", "")
        feat["data_origin"] = rec.get("data_origin", "GBIF")
        feat["review"] = rec.get("review_status", "accepted")
        feat["include"] = bool(rec.get("include_for_aoo_eoo", True))
        features.append(feat)

    provider.addFeatures(features)
    layer.updateExtents()
    return layer


def _ensure_layer_fields(layer: QgsVectorLayer, specs):
    """Add missing fields to older temporary layers created by previous plugin versions."""
    if not _valid_layer(layer):
        return
    existing = {field.name() for field in layer.fields()}
    missing = [QgsField(name, typ) for name, typ in specs if name not in existing]
    if missing:
        layer.dataProvider().addAttributes(missing)
        layer.updateFields()


def _set_attr_if_present(feat: QgsFeature, name: str, value):
    try:
        fields = feat.fields()
        idx = fields.indexFromName(name) if hasattr(fields, "indexFromName") else -1
        if idx >= 0:
            feat.setAttribute(idx, value)
    except Exception:
        pass


def create_manual_layer(layer_name: str = "AOO_EOO manual points") -> QgsVectorLayer:
    layer = QgsVectorLayer("Point?crs=EPSG:4326", layer_name, "memory")
    provider = layer.dataProvider()
    provider.addAttributes([QgsField(name, typ) for name, typ in MANUAL_FIELD_SPECS])
    layer.updateFields()
    return layer


def add_manual_feature(layer: QgsVectorLayer, point_xy: QgsPointXY, point_crs: QgsCoordinateReferenceSystem, values: dict):
    if not _valid_layer(layer):
        raise ValueError("The layer for your user points is not valid or no longer exists.")

    _ensure_layer_fields(layer, MANUAL_FIELD_SPECS)

    target_crs = layer.crs()
    point = QgsPointXY(point_xy)
    if point_crs != target_crs:
        transform = QgsCoordinateTransform(point_crs, target_crs, QgsProject.instance())
        point = transform.transform(point)

    feat = QgsFeature(layer.fields())
    feat.setGeometry(QgsGeometry.fromPointXY(point))
    data_citation = values.get("data_citation") or values.get("source_ref") or values.get("observer", "")
    identifier = values.get("identifier") or values.get("catalog_no", "")
    _set_attr_if_present(feat, "scientificName", values.get("scientificName", ""))
    _set_attr_if_present(feat, "eventDate", values.get("eventDate", ""))
    _set_attr_if_present(feat, "data_citation", data_citation)
    _set_attr_if_present(feat, "observer", values.get("observer", data_citation))
    _set_attr_if_present(feat, "source_ref", data_citation)
    _set_attr_if_present(feat, "data_origin", values.get("data_origin", "manual"))
    _set_attr_if_present(feat, "data_curator", values.get("data_curator", ""))
    _set_attr_if_present(feat, "evidence", values.get("evidence", "field_observation"))
    _set_attr_if_present(feat, "identifier", identifier)
    _set_attr_if_present(feat, "catalog_no", identifier)
    _set_attr_if_present(feat, "coordUncM", _safe_float(values.get("coordUncM"), 0.0))
    _set_attr_if_present(feat, "review", values.get("review", "review"))
    _set_attr_if_present(feat, "include", _to_bool(values.get("include", False)))
    _set_attr_if_present(feat, "notes", values.get("notes", ""))

    was_editing = layer.isEditable()
    if not was_editing:
        layer.startEditing()
    ok = layer.addFeature(feat)
    if not was_editing:
        layer.commitChanges()
    layer.updateExtents()
    layer.triggerRepaint()
    return ok


def _csv_row_get(row: dict, *names, default=""):
    """Return the first non-empty value for aliases, ignoring case and surrounding spaces."""
    lookup = {}
    for key, value in row.items():
        if key is None:
            continue
        lookup[str(key).strip().lower()] = value
    for name in names:
        value = lookup.get(str(name).strip().lower())
        if value not in (None, ""):
            return value
    return default


def import_manual_csv(layer: QgsVectorLayer, csv_path: str, default_scientific_name: str = "") -> int:
    """Import manual points from CSV.

    Accepted coordinate field aliases:
    latitudes: decimalLatitude, latitude, lat, dec_lat
    longitudes: decimalLongitude, longitude, lon, lng, dec_lon, dec_long, long
    """
    count = 0
    with open(csv_path, "r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            lat = _safe_float(_csv_row_get(row, "decimalLatitude", "latitude", "lat", "dec_lat"))
            lon = _safe_float(_csv_row_get(row, "decimalLongitude", "longitude", "lon", "lng", "dec_lon", "dec_long", "long"))
            if lat is None or lon is None:
                continue
            data_citation = _csv_row_get(row, "data_citation", "citation", "source_reference", "source_ref", "source")
            identifier = _csv_row_get(row, "identifier", "catalog_no", "catalogNumber", "id")
            values = {
                "scientificName": _csv_row_get(row, "scientificName", default=default_scientific_name),
                "eventDate": _csv_row_get(row, "eventDate", "date"),
                "data_citation": data_citation,
                "observer": _csv_row_get(row, "observer", "recordedBy", default=data_citation),
                "source_ref": data_citation,
                "data_origin": _csv_row_get(row, "data_origin", "origin_of_data", default="csv_manual"),
                "data_curator": _csv_row_get(row, "data_curator", "curator", "identifiedBy"),
                "evidence": _csv_row_get(row, "evidence", "evidence_type"),
                "identifier": identifier,
                "catalog_no": identifier,
                "coordUncM": _csv_row_get(row, "coordinateUncertaintyInMeters", "coordUncM"),
                "review": _csv_row_get(row, "review_status", "review", default="review"),
                "include": _csv_row_get(row, "include_for_aoo_eoo", "include", default=False),
                "notes": _csv_row_get(row, "notes", "comment"),
            }
            ok = add_manual_feature(layer, QgsPointXY(lon, lat), QgsCoordinateReferenceSystem("EPSG:4326"), values)
            if ok:
                count += 1
    return count


def _field_names(layer: QgsVectorLayer) -> set[str]:
    return {field.name() for field in layer.fields()}


def _get_attr(feat: QgsFeature, names: list[str], default=None):
    fields = feat.fields()
    for name in names:
        if fields.indexOf(name) >= 0:
            value = feat[name]
            if value not in (None, ""):
                return value
    return default



# A compact, pure-Python CoordinateCleaner-style screen for the most common
# suspicious coordinates. It is intentionally conservative and can be disabled
# in the GBIF tab. Full CoordinateCleaner uses richer gazetteers in R.
_SUSPICIOUS_COORDS = {
    # GBIF Secretariat / Copenhagen area
    "gbif_headquarters": [(12.5683, 55.6761), (12.5655, 55.7047)],
    # Selected country capitals that commonly appear as default georeferences
    "capital_coordinates": [
        (-3.7038, 40.4168),   # Madrid
        (-9.1393, 38.7223),   # Lisbon
        (2.3522, 48.8566),    # Paris
        (12.4964, 41.9028),   # Rome
        (-0.1276, 51.5072),   # London
        (13.4050, 52.5200),   # Berlin
        (4.9041, 52.3676),    # Amsterdam
        (-74.0721, 4.7110),   # Bogota
        (-99.1332, 19.4326),  # Mexico City
        (-58.3816, -34.6037), # Buenos Aires
        (-70.6693, -33.4489), # Santiago
        (-77.0428, -12.0464), # Lima
    ],
    # Very coarse country centroids or common map defaults. Conservative: exact/near-exact only.
    "country_centroids": [
        (-4.0, 40.0), (-8.0, 39.5), (2.0, 46.0), (12.5, 42.5),
        (-3.5, 55.0), (10.0, 51.0), (-102.0, 23.0), (-64.0, -34.0),
        (-75.0, -10.0), (-70.0, -30.0), (-55.0, -10.0),
    ],
    # Common biodiversity institution coordinates; exact/near-exact only.
    "institution_coordinates": [
        (-0.1764, 51.4967),  # Natural History Museum, London area
        (-0.2942, 51.4787),  # Kew area
        (-3.6883, 40.4113),  # Real Jardin Botanico Madrid area
        (2.3553, 48.8430),   # MNHN Paris area
        (13.2963, 52.4559),  # Botanischer Garten Berlin area
    ],
}


def _near_coord(lon, lat, lon2, lat2, tol=1e-5):
    return abs(lon - lon2) <= tol and abs(lat - lat2) <= tol


def coordinatecleaner_like_reason(record: dict):
    lat = _safe_float(record.get("decimalLatitude"))
    lon = _safe_float(record.get("decimalLongitude"))
    if lat is None or lon is None:
        return "missing coordinates"
    if not (-90 <= lat <= 90 and -180 <= lon <= 180):
        return "coordinates out of range"
    if abs(lat) < 1e-12 and abs(lon) < 1e-12:
        return "coordinates 0,0"
    if abs(lat - lon) < 1e-12:
        return "longitud igual a latitud"
    issues = str(record.get("issues") or "").upper()
    for issue in ["ZERO_COORDINATE", "COUNTRY_CENTROID", "COORDINATE_INVALID", "COORDINATE_OUT_OF_RANGE"]:
        if issue in issues:
            return f"GBIF issue {issue}"
    for label, coords in _SUSPICIOUS_COORDS.items():
        for lon2, lat2 in coords:
            if _near_coord(lon, lat, lon2, lat2):
                return label
    return None


def coordinatecleaner_filter_records(records: list[dict]):
    clean = []
    flagged = []
    for rec in records or []:
        reason = coordinatecleaner_like_reason(rec)
        if reason:
            flagged.append((rec, reason))
        else:
            clean.append(rec)
    return clean, flagged


def _extract_point_from_geometry(geom: QgsGeometry):
    """Return a QgsPointXY from a point geometry, or None for unsupported geometry.

    This avoids relying only on layer-level geometry enums, which have been
    brittle between QGIS 3 and QGIS 4.
    """
    if geom is None or geom.isEmpty():
        return None
    try:
        if geom.isMultipart():
            pts = geom.asMultiPoint()
            if pts:
                return QgsPointXY(pts[0])
        else:
            pt = geom.asPoint()
            return QgsPointXY(pt)
    except Exception:
        return None
    return None


def collect_usable_points(
    layers: list[QgsVectorLayer],
    analysis_crs: QgsCoordinateReferenceSystem,
    max_uncertainty_m=None,
    include_pending_manual: bool = False,
    deduplicate: bool = True,
):
    """Collect points transformed to analysis CRS with basic QA."""
    output = []
    excluded = []
    seen = set()

    for layer in layers:
        if not _valid_layer(layer):
            continue
        # Do not stop solely because the layer-level geometry enum is not
        # recognised. QGIS 4 can expose different enum objects; we validate
        # the geometry feature by feature below.
        is_declared_point = _is_point_layer(layer)
        transform = QgsCoordinateTransform(layer.crs(), analysis_crs, QgsProject.instance())
        names = _field_names(layer)

        for feat in layer.getFeatures():
            geom = feat.geometry()
            point = _extract_point_from_geometry(geom)
            if point is None:
                reason = "empty geometry" if geom is None or geom.isEmpty() else "geometry is not a point type"
                # Only report this as an excluded record for layers that seemed
                # to be point layers; otherwise it can be noisy.
                if is_declared_point:
                    excluded.append((layer.name(), feat.id(), reason))
                continue
            pt = transform.transform(point)

            if deduplicate:
                key = (round(pt.x(), 3), round(pt.y(), 3))
                if key in seen:
                    excluded.append((layer.name(), feat.id(), "duplicado espacial exacto aprox. 1 mm"))
                    continue
                seen.add(key)

            if "include" in names and not _to_bool(feat["include"]):
                excluded.append((layer.name(), feat.id(), "not checked for use in the calculation"))
                continue

            review_status = str(_get_attr(feat, ["review", "review_status"], "accepted")).lower()
            if review_status in {"excluded", "excluido", "reject", "rejected"}:
                excluded.append((layer.name(), feat.id(), "marked as excluded"))
                continue
            if review_status in {"pending", "review", "revisar", "pendiente"} and not include_pending_manual:
                excluded.append((layer.name(), feat.id(), "marked as review before use"))
                continue

            occurrence_status = str(_get_attr(feat, ["occStatus", "occurrenceStatus"], "PRESENT")).upper()
            if occurrence_status and occurrence_status not in {"PRESENT", ""}:
                excluded.append((layer.name(), feat.id(), f"occurrenceStatus={occurrence_status}"))
                continue

            uncertainty = _safe_float(_get_attr(feat, ["coordUncM", "coordinateUncertaintyInMeters", "uncertainty_m"], None))
            if max_uncertainty_m is not None and uncertainty is not None and uncertainty > max_uncertainty_m:
                excluded.append((layer.name(), feat.id(), f"incertidumbre {uncertainty:g} m > {max_uncertainty_m:g} m"))
                continue

            event_date = _get_attr(feat, ["eventDate", "event_date", "date"], "")
            event_year = _get_attr(feat, ["year", "event_year"], "") or _year_from_event_date(event_date)
            output.append({
                "point": pt,
                "source_layer": layer.name(),
                "scientificName": str(_get_attr(feat, ["scientificName", "sci_name"], "")),
                "eventDate": str(event_date or ""),
                "event_year": str(event_year or ""),
                "data_origin": str(_get_attr(feat, ["data_origin"], layer.name())),
                "source_ref": str(_get_attr(feat, ["data_citation", "source_ref", "datasetKey", "institution", "source"], "")),
                "source": str(_get_attr(feat, ["data_citation", "source", "source_ref", "data_origin"], "")),
                "basisofrec": str(_get_attr(feat, ["basisofrec", "basisOfRecord", "evidence"], "")),
                "catalog_no": str(_get_attr(feat, ["identifier", "catalog_no", "catalogNumber", "gbifID"], "")),
                "data_curator": str(_get_attr(feat, ["data_curator", "identifiedBy"], "")),
                "subspecies": str(_get_attr(feat, ["subspecies"], "")),
                "subpop": str(_get_attr(feat, ["subpop"], "")),
                "island": str(_get_attr(feat, ["island"], "")),
                "tax_comm": str(_get_attr(feat, ["tax_comm"], "")),
                "gbifID": str(_get_attr(feat, ["gbifID"], "")),
                "datasetKey": str(_get_attr(feat, ["datasetKey"], "")),
                "review": str(_get_attr(feat, ["review", "review_status"], "accepted")),
                "coordUncM": uncertainty,
            })
    return output, excluded


def calculate_eoo(points):
    if len(points) < 3:
        return None, 0.0
    multipoint = QgsGeometry.fromMultiPointXY(points)
    hull = multipoint.convexHull()
    if hull is None or hull.isEmpty():
        return None, 0.0
    return hull, hull.area() / 1_000_000.0


def calculate_aoo_cells(points, cell_size_m: float = 2000.0):
    occupied = set()
    for point in points:
        col = math.floor(point.x() / cell_size_m)
        row = math.floor(point.y() / cell_size_m)
        occupied.add((col, row))
    return occupied, len(occupied) * (cell_size_m * cell_size_m) / 1_000_000.0


def _add_iucn_polygon_fields(provider):
    provider.addAttributes([QgsField(name, typ) for name, typ in IUCN_POLYGON_FIELD_SPECS])


def _apply_iucn_polygon_attrs(feat: QgsFeature, attrs: dict | None, generalized_value: int):
    attrs = attrs or {}
    defaults = {
        "presence": 1,
        "origin": 1,
        "seasonal": 1,
        "compiler": "",
        "yrcompiled": datetime.now().year,
        "citation": "",
        "source": "",
        "data_sens": 0,
        "generalisd": generalized_value,
    }
    for name, _typ in IUCN_POLYGON_FIELD_SPECS:
        value = attrs.get(name, defaults.get(name, ""))
        if name == "generalisd":
            value = generalized_value

        # Required short-integer IUCN fields get safe defaults. Optional
        # numeric fields must be NULL, not an empty string, otherwise QGIS 4
        # can create a layer with fields but reject all polygon features.
        if name in {"presence", "origin", "seasonal"}:
            value = _int_or_null(value)
            if value is None:
                value = defaults.get(name, 1)
        elif name == "yrcompiled":
            value = _int_or_null(value) or datetime.now().year
        elif name == "id_no":
            value = _int_or_null(value)
        elif name in {"data_sens", "generalisd"}:
            value = 1 if _to_bool(value) else 0
        elif name == "hybas_id":
            value = _float_or_null(value)
        else:
            value = _truncate(value, 254)
        if feat.fields().indexOf(name) >= 0:
            feat[name] = value



def _set_feature_fields(feat: QgsFeature, fields):
    try:
        feat.setFields(fields, True)
    except Exception:
        pass
    return feat


def _add_features_or_raise(layer: QgsVectorLayer, features: list[QgsFeature], expected_min: int, context: str):
    """Add features to a memory layer and fail loudly if QGIS rejects them.

    Earlier versions could create an empty layer with a correct attribute table
    but no rows when QGIS 4 rejected optional numeric attributes. This helper
    makes that failure visible and tries an edit-buffer fallback before raising.
    """
    if not features:
        if expected_min > 0:
            raise ValueError(f"{context}: expected to create at least {expected_min} feature(s), but no geometries were generated.")
        return

    provider = layer.dataProvider()
    ok = False
    try:
        result = provider.addFeatures(features)
        ok = result[0] if isinstance(result, tuple) else bool(result)
    except Exception:
        ok = False

    layer.updateExtents()
    try:
        count = layer.featureCount()
    except Exception:
        count = 0

    if count >= expected_min:
        return

    # Fallback: edit-buffer insertion. Some provider-level failures are stricter
    # than layer-level addFeature in recent QGIS builds.
    try:
        if not layer.isEditable():
            layer.startEditing()
        for feat in features:
            layer.addFeature(feat)
        layer.commitChanges()
        layer.updateExtents()
        count = layer.featureCount()
    except Exception as exc:
        raise ValueError(f"{context}: QGIS no pudo insertar entidades en la capa ({exc}).")

    if count < expected_min:
        raise ValueError(
            f"{context}: QGIS created the layer, but did not insert features "
            f"({count}/{expected_min}). Revise tipos de campos o CRS."
        )

def create_aoo_grid_layer(occupied_cells, crs: QgsCoordinateReferenceSystem, cell_size_m: float, iucn_attrs: dict | None = None) -> QgsVectorLayer:
    layer = QgsVectorLayer(f"Polygon?crs={crs.authid()}", "AOO occupied cells", "memory")
    provider = layer.dataProvider()
    provider.addAttributes([
        QgsField("cell_id", QVariant.String),
        QgsField("area_km2", QVariant.Double),
    ])
    _add_iucn_polygon_fields(provider)
    layer.updateFields()

    features = []
    for col, row in sorted(occupied_cells):
        x0 = col * cell_size_m
        y0 = row * cell_size_m
        x1 = x0 + cell_size_m
        y1 = y0 + cell_size_m
        polygon = QgsGeometry.fromPolygonXY([[QgsPointXY(x0, y0), QgsPointXY(x1, y0), QgsPointXY(x1, y1), QgsPointXY(x0, y1), QgsPointXY(x0, y0)]])
        feat = QgsFeature(layer.fields())
        feat.setGeometry(polygon)
        feat["cell_id"] = f"{col}_{row}"
        feat["area_km2"] = (cell_size_m * cell_size_m) / 1_000_000.0
        _apply_iucn_polygon_attrs(feat, iucn_attrs, generalized_value=0)
        features.append(feat)

    _add_features_or_raise(layer, features, expected_min=len(occupied_cells), context="AOO occupied cells")
    layer.updateExtents()
    return layer


def create_eoo_layer(hull: QgsGeometry, crs: QgsCoordinateReferenceSystem, eoo_km2: float, iucn_attrs: dict | None = None) -> QgsVectorLayer:
    layer = QgsVectorLayer(f"Polygon?crs={crs.authid()}", "EOO convex hull", "memory")
    provider = layer.dataProvider()
    provider.addAttributes([
        QgsField("method", QVariant.String),
        QgsField("eoo_km2", QVariant.Double),
    ])
    _add_iucn_polygon_fields(provider)
    layer.updateFields()
    feat = QgsFeature(layer.fields())
    feat.setGeometry(hull)
    feat["method"] = "minimum convex polygon"
    feat["eoo_km2"] = eoo_km2
    _apply_iucn_polygon_attrs(feat, iucn_attrs, generalized_value=1)
    _add_features_or_raise(layer, [feat], expected_min=1, context="EOO convex hull")
    layer.updateExtents()
    return layer


def create_used_points_layer(records, crs: QgsCoordinateReferenceSystem) -> QgsVectorLayer:
    layer = QgsVectorLayer(f"Point?crs={crs.authid()}", "AOO_EOO points used", "memory")
    provider = layer.dataProvider()
    provider.addAttributes([QgsField(name, typ) for name, typ in USED_POINT_FIELD_SPECS])
    layer.updateFields()

    features = []
    for rec in records:
        feat = QgsFeature(layer.fields())
        feat.setGeometry(QgsGeometry.fromPointXY(rec["point"]))
        feat["scientificName"] = rec.get("scientificName", "")
        feat["data_origin"] = rec.get("data_origin", "")
        feat["source_ref"] = rec.get("source_ref", "")
        feat["gbifID"] = rec.get("gbifID", "")
        feat["datasetKey"] = rec.get("datasetKey", "")
        feat["review"] = rec.get("review", "")
        feat["coordUncM"] = rec.get("coordUncM")
        features.append(feat)
    _add_features_or_raise(layer, features, expected_min=len(records), context="AOO_EOO points used")
    layer.updateExtents()
    return layer


def assess_iucn_criterion_b(aoo_km2, eoo_km2, inputs: dict | None = None) -> dict:
    """Return an orientative category using only IUCN Criterion B area thresholds.

    This is not a formal Red List category because Criterion B also requires
    additional subconditions. It simply reports the highest threat category
    reached by EOO and/or AOO thresholds.
    """

    def area_category(value, thresholds, metric_name):
        try:
            value = float(value)
        except Exception:
            return "Not evaluable", f"{metric_name} not available"
        if value <= 0:
            return "Not evaluable", f"{metric_name} not available"
        for cat, threshold in thresholds:
            if value < threshold:
                return cat, f"{metric_name} < {threshold:g} km²"
        return "No alcanza umbral VU", f"{metric_name} no alcanza umbral VU"

    eoo_category, eoo_reason = area_category(eoo_km2, [("CR", 100), ("EN", 5000), ("VU", 20000)], "EOO")
    aoo_category, aoo_reason = area_category(aoo_km2, [("CR", 10), ("EN", 500), ("VU", 2000)], "AOO")

    order = {"CR": 0, "EN": 1, "VU": 2, "Does not reach VU threshold": 3, "Not evaluable": 4}
    candidates = [c for c in [eoo_category, aoo_category] if c in ("CR", "EN", "VU")]
    if candidates:
        combined = sorted(candidates, key=lambda c: order[c])[0]
    elif eoo_category == "Not evaluable" and aoo_category == "Not evaluable":
        combined = "Not evaluable"
    else:
        combined = "No alcanza umbral VU"

    return {
        "category": combined,
        "eoo_category": eoo_category,
        "aoo_category": aoo_category,
        "eoo_reason": eoo_reason,
        "aoo_reason": aoo_reason,
        "explanation": "Indicative category calculated only from the EOO and AOO thresholds of Criterion B. It is not a formal IUCN assessment.",
    }

def run_aoo_eoo(
    layers: list[QgsVectorLayer],
    analysis_crs_authid: str = "EPSG:3035",
    cell_size_m: float = 2000.0,
    max_uncertainty_m=None,
    include_pending_manual: bool = False,
    deduplicate: bool = True,
    iucn_polygon_attrs: dict | None = None,
    iucn_b_inputs: dict | None = None,
) -> dict:
    analysis_crs = QgsCoordinateReferenceSystem(analysis_crs_authid)
    if not analysis_crs.isValid():
        raise ValueError(f"Invalid CRS: {analysis_crs_authid}")
    if hasattr(analysis_crs, "isGeographic") and analysis_crs.isGeographic():
        raise ValueError(
            "The analysis CRS is geographic and uses degrees, not metres. "
            "AOO/EOO grid calculations require a projected CRS in metres, for example EPSG:3035 for Europe or EPSG:25830 for much of Spain. "
            "GBIF/SRedList Point Distribution exports are still produced in WGS84/EPSG:4326.\n"
            "ES: El CRS de análisis es geográfico y usa grados, no metros. "
            "El cálculo de la cuadrícula AOO/EOO requiere un CRS proyectado en metros, por ejemplo EPSG:3035 para Europa o EPSG:25830 para gran parte de España. "
            "Las salidas Point Distribution para GBIF/SRedList siguen generándose en WGS84/EPSG:4326."
        )

    source_layer_summary = []
    for layer in layers:
        try:
            source_layer_summary.append(f"{layer.name()}={layer.featureCount()}")
        except Exception:
            source_layer_summary.append("capa no legible")

    usable, excluded = collect_usable_points(
        layers,
        analysis_crs,
        max_uncertainty_m=max_uncertainty_m,
        include_pending_manual=include_pending_manual,
        deduplicate=deduplicate,
    )
    points = [rec["point"] for rec in usable]
    if not points:
        reasons = {}
        for _layer_name, _fid, reason in excluded:
            reasons[reason] = reasons.get(reason, 0) + 1
        detail = "; ".join(f"{k}: {v}" for k, v in sorted(reasons.items())) or "no point records detected"
        raise ValueError(
            "There are no valid points to calculate AOO/EOO. "
            f"Layers reviewed: {', '.join(source_layer_summary)}. "
            f"Motivos principales: {detail}."
        )
    hull, eoo_km2 = calculate_eoo(points)
    occupied_cells, aoo_km2 = calculate_aoo_cells(points, cell_size_m=cell_size_m)

    used_layer = create_used_points_layer(usable, analysis_crs)
    aoo_layer = create_aoo_grid_layer(occupied_cells, analysis_crs, cell_size_m, iucn_polygon_attrs)
    eoo_layer = create_eoo_layer(hull, analysis_crs, eoo_km2, iucn_polygon_attrs) if hull is not None else None
    iucn_criterion_b = assess_iucn_criterion_b(aoo_km2, eoo_km2, iucn_b_inputs)

    return {
        "analysis_crs": analysis_crs_authid,
        "cell_size_m": cell_size_m,
        "n_used": len(usable),
        "n_excluded": len(excluded),
        "n_cells": len(occupied_cells),
        "aoo_km2": aoo_km2,
        "eoo_km2": eoo_km2,
        "used_layer": used_layer,
        "aoo_layer": aoo_layer,
        "eoo_layer": eoo_layer,
        "excluded": excluded,
        "used_records": usable,
        "iucn_polygon_attrs": iucn_polygon_attrs or {},
        "source_layer_summary": source_layer_summary,
        "iucn_criterion_b": iucn_criterion_b,
    }


def _html_escape(value) -> str:
    text = "" if value is None else str(value)
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def _gbif_dataset_counts(used_records):
    counts = {}
    missing = 0
    for rec in used_records or []:
        if rec.get("gbifID"):
            key = (rec.get("datasetKey") or "").strip()
            if key:
                counts[key] = counts.get(key, 0) + 1
            else:
                missing += 1
    return counts, missing


def create_table_layer(layer_name: str, field_specs) -> QgsVectorLayer:
    """Create a non-spatial memory table and add the requested fields."""
    layer = QgsVectorLayer("None", layer_name, "memory")
    provider = layer.dataProvider()
    provider.addAttributes([QgsField(name, typ) for name, typ in field_specs])
    layer.updateFields()
    return layer


def _add_table_row(layer: QgsVectorLayer, values: dict):
    feat = QgsFeature(layer.fields())
    for field in layer.fields():
        name = field.name()
        feat[name] = values.get(name, "")
    layer.dataProvider().addFeature(feat)


def create_report_layers(result: dict) -> dict:
    """Create in-project report tables instead of writing files by default."""
    summary = create_table_layer("AOO_EOO report summary", REPORT_FIELD_SPECS)
    rows = []
    iucn_b = result.get("iucn_criterion_b", {}) or {}

    # Keep all AOO/EOO parameters together to make the summary easier to read.
    resumen_order = [
        ("taxon", result.get("taxon_name", "")),
        ("taxonKey", result.get("taxon_key", "")),
        ("analysis_crs", result.get("analysis_crs", "")),
        ("cell_size_m", result.get("cell_size_m", "")),
        ("n_used", result.get("n_used", "")),
        ("n_excluded", result.get("n_excluded", "")),
        ("n_cells", result.get("n_cells", "")),
        ("aoo_km2", result.get("aoo_km2", "")),
        ("aoo_category", iucn_b.get("aoo_category", "")),
        ("aoo_reason", iucn_b.get("aoo_reason", "")),
        ("eoo_km2", result.get("eoo_km2", "")),
        ("eoo_category", iucn_b.get("eoo_category", "")),
        ("eoo_reason", iucn_b.get("eoo_reason", "")),
    ]
    for key, value in resumen_order:
        rows.append({"seccion": "resumen_aoo_eoo", "campo": key, "valor": value})

    rows.append({"seccion": "diagnostico", "campo": "capas_revisadas", "valor": "; ".join(result.get("source_layer_summary", []))})
    rows.append({"seccion": "metodo", "campo": "AOO", "valor": "celdas ocupadas; por defecto 2 x 2 km"})
    rows.append({"seccion": "method", "campo": "EOO", "valor": "minimum convex polygon / convex hull"})
    rows.append({"seccion": "iucn_categoria_por_aoo_eoo", "campo": "aoo_category", "valor": iucn_b.get("aoo_category", "")})
    rows.append({"seccion": "iucn_categoria_por_aoo_eoo", "campo": "eoo_category", "valor": iucn_b.get("eoo_category", "")})
    rows.append({"seccion": "warning", "campo": "review", "valor": "AOO/EOO categories are indicative and are based only on spatial thresholds. A formal IUCN assessment requires review of additional Criterion B conditions and other applicable criteria."})

    gbif_ids = sorted({str(rec.get("gbifID") or "").strip() for rec in result.get("used_records", []) if str(rec.get("gbifID") or "").strip()})
    non_gbif = sum(1 for rec in result.get("used_records", []) if not str(rec.get("gbifID") or "").strip())
    rows.append({"seccion": "cita_gbif", "campo": "gbif_records_with_gbifID", "valor": len(gbif_ids)})
    rows.append({"seccion": "cita_gbif", "campo": "non_gbif_or_without_gbifID_records", "valor": non_gbif})
    rows.append({"seccion": "gbif_citation", "campo": "recommended_action", "valor": "Use tab 5 to request from GBIF an official download for the gbifIDs used and cite the resulting DOI."})
    for row in rows:
        _add_table_row(summary, row)
    summary.updateExtents()

    excluded = create_table_layer("AOO_EOO unused records", EXCLUDED_FIELD_SPECS)
    for layer_name, fid, reason in result.get("excluded", []):
        _add_table_row(excluded, {"source_layer": layer_name, "feature_id": str(fid), "reason": reason})
    excluded.updateExtents()

    return {"summary": summary, "excluded": excluded}



def point_distribution_rows_from_result(result: dict, settings: dict) -> list[dict]:
    """Build rows that match the IUCN Point Distribution attributes."""
    analysis_crs = QgsCoordinateReferenceSystem(result.get("analysis_crs", "EPSG:3035"))
    wgs84 = QgsCoordinateReferenceSystem("EPSG:4326")
    transform = QgsCoordinateTransform(analysis_crs, wgs84, QgsProject.instance())
    rows = []
    for rec in result.get("used_records", []):
        wgs_point = transform.transform(rec["point"])
        source_value = rec.get("source_ref") or rec.get("source") or settings.get("source", "")
        basis_value = _basis_to_iucn(rec.get("basisofrec") or settings.get("basisofrec", ""))
        row = {
            "sci_name": _truncate(settings.get("sci_name") or rec.get("scientificName", ""), 100),
            "presence": _int_or_blank(settings.get("presence", 1)) or 1,
            "origin": _int_or_blank(settings.get("origin", 1)) or 1,
            "seasonal": _int_or_blank(settings.get("seasonal", 1)) or 1,
            "compiler": _truncate(settings.get("compiler", ""), 254),
            "yrcompiled": _int_or_blank(settings.get("yrcompiled", "")),
            "citation": _truncate(settings.get("citation", ""), 254),
            "dec_lat": round(float(wgs_point.y()), 8),
            "dec_long": round(float(wgs_point.x()), 8),
            "spatialref": _truncate(settings.get("spatialref", "WGS84"), 100),
            "subspecies": _truncate(rec.get("subspecies") or settings.get("subspecies", ""), 100),
            "subpop": _truncate(rec.get("subpop") or settings.get("subpop", ""), 100),
            "data_sens": _int_or_blank(settings.get("data_sens", 0)) or 0,
            "sens_comm": _truncate(settings.get("sens_comm", ""), 254),
            "event_year": _int_or_blank(rec.get("event_year") or settings.get("event_year", "")),
            "source": _truncate(source_value, 254),
            "basisofrec": _truncate(basis_value, 30),
            "catalog_no": _truncate(rec.get("catalog_no") or rec.get("gbifID", ""), 254),
            "dist_comm": _truncate(settings.get("dist_comm", ""), 254),
            "island": _truncate(rec.get("island") or settings.get("island", ""), 150),
            "tax_comm": _truncate(rec.get("tax_comm") or settings.get("tax_comm", ""), 254),
        }
        rows.append({field: row.get(field, "") for field in POINT_DISTRIBUTION_FIELDS})
    return rows


def create_point_distribution_layer(result: dict, settings: dict) -> QgsVectorLayer:
    layer = create_table_layer("Point distribution CSV", POINT_DISTRIBUTION_FIELD_SPECS)
    for row in point_distribution_rows_from_result(result, settings):
        _add_table_row(layer, row)
    layer.updateExtents()
    return layer


def create_point_distribution_shapefile_layer(result: dict, settings: dict) -> QgsVectorLayer:
    """Create a point layer in WGS84 with the exact Point Distribution attributes."""
    layer = QgsVectorLayer("Point?crs=EPSG:4326", "Point distribution shapefile", "memory")
    provider = layer.dataProvider()
    provider.addAttributes([QgsField(name, typ) for name, typ in POINT_DISTRIBUTION_FIELD_SPECS])
    layer.updateFields()

    features = []
    for row in point_distribution_rows_from_result(result, settings):
        lat = _safe_float(row.get("dec_lat"))
        lon = _safe_float(row.get("dec_long"))
        if lat is None or lon is None:
            continue
        feat = QgsFeature(layer.fields())
        feat.setGeometry(QgsGeometry.fromPointXY(QgsPointXY(lon, lat)))
        for field_name in POINT_DISTRIBUTION_FIELDS:
            field_index = feat.fields().indexOf(field_name)
            if field_index >= 0:
                field = feat.fields().field(field_index)
                feat[field_name] = _value_for_qgis_field(field, row.get(field_name, ""))
        features.append(feat)

    _add_features_or_raise(layer, features, expected_min=len(features), context="Point Distribution shapefile")
    layer.updateExtents()
    return layer


def write_point_distribution_shapefile(result: dict, settings: dict, shp_path: str) -> int:
    """Write Point Distribution as ESRI Shapefile and return number of features."""
    layer = create_point_distribution_shapefile_layer(result, settings)
    options = QgsVectorFileWriter.SaveVectorOptions()
    options.driverName = "ESRI Shapefile"
    options.fileEncoding = "UTF-8"
    options.layerName = os.path.splitext(os.path.basename(shp_path))[0]
    transform_context = QgsProject.instance().transformContext()
    error = QgsVectorFileWriter.writeAsVectorFormatV3(layer, shp_path, transform_context, options)
    # QGIS 3/4 returns tuple-like values. The first element is error code.
    err_code = error[0] if isinstance(error, tuple) else error
    try:
        no_error = QgsVectorFileWriter.NoError
    except AttributeError:
        no_error = 0
    if err_code != no_error:
        err_msg = error[1] if isinstance(error, tuple) and len(error) > 1 else str(error)
        raise ValueError(f"No se pudo guardar el shapefile Point Distribution: {err_msg}")
    return layer.featureCount()


def write_point_distribution_csv(result: dict, settings: dict, csv_path: str) -> int:
    rows = point_distribution_rows_from_result(result, settings)
    with open(csv_path, "w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=POINT_DISTRIBUTION_FIELDS)
        writer.writeheader()
        writer.writerows(rows)
    return len(rows)


def create_point_distribution_field_guide_layer() -> QgsVectorLayer:
    layer = create_table_layer("Point Distribution campos", IUCN_POINT_FIELD_GUIDE_SPECS)
    for field, definition, requirement, field_type, notes in IUCN_POINT_FIELD_GUIDE:
        _add_table_row(layer, {
            "field": field,
            "definition": definition,
            "requirement": requirement,
            "type": field_type,
            "notes": notes,
        })
    layer.updateExtents()
    return layer


def create_gbif_derived_dataset_result_layer(response: dict) -> QgsVectorLayer:
    layer = create_table_layer("GBIF Derived Dataset DOI", REPORT_FIELD_SPECS)
    for key in ["doi", "citation", "title", "sourceUrl", "description"]:
        _add_table_row(layer, {"seccion": "GBIF Derived Dataset", "campo": key, "valor": response.get(key, "")})
    for key, value in response.items():
        if key not in {"doi", "citation", "title", "sourceUrl", "description"}:
            _add_table_row(layer, {"seccion": "GBIF Derived Dataset raw", "campo": key, "valor": value})
    layer.updateExtents()
    return layer


def write_report(result: dict, folder=None):
    folder = folder or tempfile.gettempdir()
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    csv_path = os.path.join(folder, f"aoo_eoo_report_{stamp}.csv")
    json_path = os.path.join(folder, f"aoo_eoo_metadata_{stamp}.json")
    html_path = os.path.join(folder, f"aoo_eoo_informe_final_{stamp}.html")
    derived_path = os.path.join(folder, f"gbif_derived_dataset_datasetKey_counts_{stamp}.csv")

    used_records = result.get("used_records", [])
    gbif_counts, gbif_missing_dataset = _gbif_dataset_counts(used_records)
    gbif_used_total = sum(gbif_counts.values()) + gbif_missing_dataset

    with open(csv_path, "w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["seccion", "campo", "valor"])
        writer.writerow(["summary", "taxon", result.get("taxon_name", "")])
        writer.writerow(["summary", "taxonKey", result.get("taxon_key", "")])
        for key in ["analysis_crs", "cell_size_m", "n_used", "n_excluded", "n_cells", "aoo_km2", "eoo_km2"]:
            writer.writerow(["summary", key, result.get(key)])
        writer.writerow([])
        writer.writerow(["cita_gbif", "gbif_records_used", gbif_used_total])
        writer.writerow(["cita_gbif", "gbif_datasets_used", len(gbif_counts)])
        writer.writerow(["cita_gbif", "derived_dataset_counts_file", derived_path if gbif_counts else ""])
        writer.writerow(["gbif_citation", "recommended_action", "Request from GBIF an official download for the gbifIDs used and cite the resulting DOI."])
        writer.writerow([])
        writer.writerow(["datasetKey", "count", ""])
        for dataset_key, count in sorted(gbif_counts.items()):
            writer.writerow([dataset_key, count, ""])
        if gbif_missing_dataset:
            writer.writerow(["GBIF records without datasetKey in used layer", gbif_missing_dataset, ""])
        writer.writerow([])
        writer.writerow(["excluded_layer", "feature_id", "reason"])
        for layer_name, fid, reason in result.get("excluded", []):
            writer.writerow([layer_name, fid, reason])

    if gbif_counts:
        with open(derived_path, "w", encoding="utf-8", newline="") as handle:
            writer = csv.writer(handle)
            writer.writerow(["datasetKey", "count"])
            for dataset_key, count in sorted(gbif_counts.items()):
                writer.writerow([dataset_key, count])
    else:
        derived_path = None

    metadata = {key: result.get(key) for key in ["analysis_crs", "cell_size_m", "n_used", "n_excluded", "n_cells", "aoo_km2", "eoo_km2"]}
    metadata["taxon_name"] = result.get("taxon_name", "")
    metadata["taxon_key"] = result.get("taxon_key", "")
    metadata["gbif_query_params"] = result.get("gbif_query_params", {})
    metadata["gbif_citation"] = {
        "gbif_records_used": gbif_used_total,
        "gbif_datasets_used": len(gbif_counts),
        "derived_dataset_counts_file": derived_path,
        "recommendation": "Use the plugin GBIF DOI tab to request an official GBIF occurrence download by the exact gbifID records used and cite the resulting DOI.",
    }
    metadata["method"] = {
        "AOO": "occupied grid cells; default 2 x 2 km = 4 km2 per cell",
        "EOO": "minimum convex polygon / convex hull",
        "warning": "Review outliers and coordinate uncertainty before using results in formal assessments.",
    }
    with open(json_path, "w", encoding="utf-8") as handle:
        json.dump(metadata, handle, indent=2, ensure_ascii=False)

    today = datetime.now().strftime("%Y-%m-%d")
    query_params_html = _html_escape(json.dumps(result.get("gbif_query_params", {}), ensure_ascii=False, indent=2))
    dataset_rows = "\n".join(
        f"<tr><td>{_html_escape(dataset_key)}</td><td>{count}</td></tr>"
        for dataset_key, count in sorted(gbif_counts.items())
    ) or '<tr><td colspan="2">No GBIF records with datasetKey were used in this calculation.</td></tr>'
    excluded_rows = "\n".join(
        f"<tr><td>{_html_escape(layer)}</td><td>{_html_escape(fid)}</td><td>{_html_escape(reason)}</td></tr>"
        for layer, fid, reason in result.get("excluded", [])[:500]
    ) or '<tr><td colspan="3">There are no excluded records.</td></tr>'

    if gbif_counts:
        citation_text = (
            f"Datos de ocurrencia mediados por GBIF consultados el {today} mediante la GBIF Occurrence API. "
            f"The calculation used {gbif_used_total} GBIF records from {len(gbif_counts)} datasets. "
            "For a publication or formal report, use tab 5 to request from GBIF an official download for the gbifIDs used and cite the resulting DOI."
        )
    else:
        citation_text = (
            "This calculation does not contain GBIF records identifiable with datasetKey. "
            "If you used an external GBIF layer, keep the gbifID and datasetKey fields so that you can generate the recommended citation."
        )

    html = f"""<!doctype html>
<html lang="es">
<head>
<meta charset="utf-8">
<title>Informe final AOO/EOO</title>
<style>
body {{ font-family: Arial, sans-serif; margin: 2rem; line-height: 1.45; }}
table {{ border-collapse: collapse; width: 100%; margin: 1rem 0; }}
th, td {{ border: 1px solid #ccc; padding: 0.35rem; text-align: left; }}
th {{ background: #f0f0f0; }}
code, pre {{ background: #f6f6f6; padding: 0.2rem; }}
.warning {{ background: #fff4d6; border: 1px solid #e5c56b; padding: 0.8rem; }}
</style>
</head>
<body>
<h1>Informe final AOO/EOO</h1>
<p><strong>Calculation date:</strong> {_html_escape(today)}</p>
<p><strong>Taxon:</strong> {_html_escape(result.get('taxon_name', ''))}</p>
<p><strong>taxonKey GBIF:</strong> {_html_escape(result.get('taxon_key', ''))}</p>

<h2>Resultados</h2>
<table>
<tr><th>Metric</th><th>Value</th></tr>
<tr><td>Analysis CRS</td><td>{_html_escape(result.get('analysis_crs'))}</td></tr>
<tr><td>AOO cell size</td><td>{_html_escape(result.get('cell_size_m'))} m</td></tr>
<tr><td>Used records</td><td>{_html_escape(result.get('n_used'))}</td></tr>
<tr><td>Excluded records</td><td>{_html_escape(result.get('n_excluded'))}</td></tr>
<tr><td>Celdas AOO ocupadas</td><td>{_html_escape(result.get('n_cells'))}</td></tr>
<tr><td>AOO</td><td>{result.get('aoo_km2', 0):.4f} km²</td></tr>
<tr><td>EOO</td><td>{result.get('eoo_km2', 0):.4f} km²</td></tr>
</table>

<h2>How to cite the GBIF data used</h2>
<p>{_html_escape(citation_text)}</p>
<div class="warning">
<strong>Important:</strong> this version allows you to request from tab 5 an official GBIF download using the <code>gbifID</code> that actually entered the calculation. When GBIF completes the download, it will return a citable DOI.
</div>
<p><strong>Texto provisional hasta obtener el DOI:</strong></p>
<blockquote>{_html_escape(citation_text)}</blockquote>
<p><strong>When you obtain the DOI from GBIF, use a citation like this:</strong></p>
<blockquote>GBIF.org ({today}). GBIF Occurrence Download. https://doi.org/[DOI asignado por GBIF]</blockquote>

<h3>GBIF datasets used</h3>
<table>
<tr><th>datasetKey</th><th>No. used records</th></tr>
{dataset_rows}
</table>

<h2>Filtros GBIF utilizados</h2>
<pre>{query_params_html}</pre>

<h2>Method</h2>
<p><strong>AOO:</strong> number of occupied cells multiplied by the area of each cell. The standard option proposed in the interface is 2 × 2 km.</p>
<p><strong>EOO:</strong> minimum convex polygon / convex hull calculated from the points used.</p>

<h2>Excluded records</h2>
<table>
<tr><th>Layer</th><th>Internal ID</th><th>Reason</th></tr>
{excluded_rows}
</table>
</body>
</html>
"""
    with open(html_path, "w", encoding="utf-8") as handle:
        handle.write(html)

    return csv_path, json_path, html_path, derived_path


def create_iucn_polygon_field_guide_layer() -> QgsVectorLayer:
    layer = create_table_layer("IUCN atributos AOO EOO campos", IUCN_FIELD_GUIDE_SPECS)
    for row in IUCN_POLYGON_FIELD_GUIDE:
        field, definition, requirement = row[0], row[1], row[2]
        _add_table_row(layer, {
            "field": field,
            "definition": definition,
            "requirement": requirement,
        })
    layer.updateExtents()
    return layer



def create_gbif_occurrence_download_result_layer(response: dict) -> QgsVectorLayer:
    """Create a small QGIS table with the official GBIF occurrence download DOI/status."""
    layer = create_table_layer("GBIF Occurrence Download DOI", REPORT_FIELD_SPECS)
    for key in ["key", "status", "doi", "citation", "downloadLink", "created", "modified", "numberRecords"]:
        value = response.get(key, "") if isinstance(response, dict) else ""
        _add_table_row(layer, {"seccion": "GBIF Occurrence Download", "campo": key, "valor": value})
    if isinstance(response, dict):
        for key, value in response.items():
            if key not in {"key", "status", "doi", "citation", "downloadLink", "created", "modified", "numberRecords"}:
                if key in {"request", "downloadLink", "licenseCounts", "datasets"}:
                    value = json.dumps(value, ensure_ascii=False)[:5000]
                _add_table_row(layer, {"seccion": "GBIF Occurrence Download raw", "campo": key, "valor": value})
    layer.updateExtents()
    return layer
