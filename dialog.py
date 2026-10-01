# -*- coding: utf-8 -*-
"""Dialog and UI for the AOO/EOO GBIF plugin."""

from __future__ import annotations

from datetime import datetime
import os
import re

from qgis.PyQt.QtCore import Qt, QUrl
from qgis.PyQt.QtWidgets import (
    QApplication,
    QAbstractItemView,
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QTabWidget,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)
from qgis.PyQt.QtGui import QDesktopServices
from qgis.gui import QgsMapLayerComboBox
from qgis.core import (
    QgsCoordinateReferenceSystem,
    QgsCoordinateTransform,
    QgsGeometry,
    QgsProject,
    QgsMapLayerProxyModel,
    Qgis,
    QgsPointXY,
    QgsVectorLayer,
    QgsFeature,
    QgsField,
)
try:
    from qgis.PyQt.QtCore import QVariant
except ImportError:  # pragma: no cover
    class QVariant:
        String = str
        Int = int
        Double = float
        Bool = bool


def _qt_item_user_checkable():
    try:
        return Qt.ItemIsUserCheckable
    except AttributeError:
        return Qt.ItemFlag.ItemIsUserCheckable


def _qt_checked():
    try:
        return Qt.Checked
    except AttributeError:
        return Qt.CheckState.Checked


def _qt_unchecked():
    try:
        return Qt.Unchecked
    except AttributeError:
        return Qt.CheckState.Unchecked


def _qt_user_role():
    try:
        return Qt.UserRole
    except AttributeError:
        return Qt.ItemDataRole.UserRole


def _qt_item_is_enabled():
    try:
        return Qt.ItemIsEnabled
    except AttributeError:
        return Qt.ItemFlag.ItemIsEnabled


def _qt_item_is_selectable():
    try:
        return Qt.ItemIsSelectable
    except AttributeError:
        return Qt.ItemFlag.ItemIsSelectable


def _dialog_accepted():
    try:
        return QDialog.Accepted
    except AttributeError:
        return QDialog.DialogCode.Accepted


def _dialog_exec(dialog):
    if hasattr(dialog, "exec"):
        return dialog.exec()
    return dialog.exec_()


def _button_box_ok():
    try:
        return QDialogButtonBox.Ok
    except AttributeError:
        return QDialogButtonBox.StandardButton.Ok


def _button_box_cancel():
    try:
        return QDialogButtonBox.Cancel
    except AttributeError:
        return QDialogButtonBox.StandardButton.Cancel




def _set_form_expanding_fields(form):
    """Set QFormLayout fields to grow in Qt5/Qt6-compatible way."""
    try:
        policy = QFormLayout.ExpandingFieldsGrow
    except AttributeError:
        try:
            policy = QFormLayout.FieldGrowthPolicy.ExpandingFieldsGrow
        except AttributeError:
            return
    form.setFieldGrowthPolicy(policy)



def _messagebox_yes():
    try:
        return QMessageBox.Yes
    except AttributeError:
        return QMessageBox.StandardButton.Yes


def _messagebox_no():
    try:
        return QMessageBox.No
    except AttributeError:
        return QMessageBox.StandardButton.No

def _line_edit_password():
    try:
        return QLineEdit.Password
    except AttributeError:
        return QLineEdit.EchoMode.Password


def _point_layer_filter():
    """QGIS 3.34+ and QGIS 4 moved layer filter enums to Qgis.LayerFilter."""
    try:
        return Qgis.LayerFilter.PointLayer
    except AttributeError:  # QGIS 3.28-3.32
        return QgsMapLayerProxyModel.PointLayer

def _layer_is_usable(layer) -> bool:
    """Return False when a QGIS layer wrapper points to an object already deleted by QGIS."""
    if layer is None:
        return False
    try:
        return layer.isValid()
    except RuntimeError:
        return False


def _layer_name(layer, fallback: str = "") -> str:
    try:
        return layer.name() if layer is not None else fallback
    except RuntimeError:
        return fallback


from .gbif_client import (
    GbifError,
    match_species,
    occurrence_facets,
    search_occurrences,
    slim_record,
    request_occurrence_download_by_gbif_ids,
    get_occurrence_download,
)
from .manual_point_tool import ManualPointTool, ManualRectangleTool
from .processing_logic import (
    add_manual_feature,
    create_manual_layer,
    create_occurrence_layer,
    import_manual_csv,
    run_aoo_eoo,
    create_report_layers,
    create_point_distribution_layer,
    write_point_distribution_csv,
    create_point_distribution_shapefile_layer,
    write_point_distribution_shapefile,
    create_iucn_polygon_field_guide_layer,
    create_gbif_derived_dataset_result_layer,
    create_gbif_occurrence_download_result_layer,
    coordinatecleaner_filter_records,
)


BASIS_OPTIONS = [
    ("HUMAN_OBSERVATION", True, "Include: human observation; review identity and spatial precision."),
    ("PRESERVED_SPECIMEN", True, "Include with control: vouchers or specimens; review date and georeferencing."),
    ("MACHINE_OBSERVATION", False, "Review: cameras, sensors or automatic identification. Not included by default."),
    ("MATERIAL_SAMPLE", False, "Review: physical or environmental sample."),
    ("MATERIAL_CITATION", False, "Review: material citation; possible duplicate or low precision."),
    ("OCCURRENCE", False, "Review: generic category."),
    ("OBSERVATION", False, "Review: generic category."),
    ("LIVING_SPECIMEN", False, "Excluir por defecto: puede ser ex situ o cultivado."),
    ("FOSSIL_SPECIMEN", False, "Exclude by default for current distribution."),
    ("UNKNOWN", False, "Exclude/Review: unknown record type."),
]

ESTABLISHMENT_OPTIONS = [
    ("NATIVE", True, "Include: native population."),
    ("NATIVE_REINTRODUCED", True, "Include/Review: reintroduction within the native area."),
    ("INTRODUCED", False, "Exclude by default in native-distribution assessment."),
    ("INTRODUCED_ASSISTED_COLONISATION", False, "Exclude/Review depending on objective."),
    ("VAGRANT", False, "Exclude: does not represent stable occupancy."),
    ("UNCERTAIN", False, "Revisar: origen incierto."),
]


class ManualFeatureDialog(QDialog):
    """Small form for one user-added occurrence."""

    def __init__(self, parent=None, default_name: str = "", show_coordinates: bool = False):
        super().__init__(parent)
        self.show_coordinates = show_coordinates
        title = "Add point by coordinates" if show_coordinates else "Add user point for AOO/EOO"
        self.setWindowTitle(title)
        layout = QVBoxLayout(self)
        form = QFormLayout()
        _set_form_expanding_fields(form)

        self.scientific_name = QLineEdit(default_name)
        self.event_date = QLineEdit(datetime.now().strftime("%Y-%m-%d"))

        self.latitude = None
        self.longitude = None
        if show_coordinates:
            coord_note = QLabel("Enter decimal coordinates in WGS84 / EPSG:4326.")
            coord_note.setWordWrap(True)
            layout.addWidget(coord_note)
            self.latitude = QDoubleSpinBox()
            self.latitude.setRange(-90.0, 90.0)
            self.latitude.setDecimals(8)
            self.latitude.setSingleStep(0.0001)
            self.latitude.setValue(0.0)
            self.longitude = QDoubleSpinBox()
            self.longitude.setRange(-180.0, 180.0)
            self.longitude.setDecimals(8)
            self.longitude.setSingleStep(0.0001)
            self.longitude.setValue(0.0)

        self.data_origin_text = QLineEdit()
        self.data_origin_text.setPlaceholderText("E.g.: fieldwork, herbarium, bibliography, report")
        self.data_curator = QLineEdit()
        self.evidence = QComboBox()
        self.evidence.addItems(["voucher/specimen", "field observation", "photograph", "report", "bibliography", "other"])
        self.identifier = QLineEdit()
        self.uncertainty = QDoubleSpinBox()
        self.uncertainty.setRange(0, 1_000_000)
        self.uncertainty.setDecimals(2)
        self.uncertainty.setValue(4)
        self.uncertainty.setSuffix(" m")
        self.review = QComboBox()
        self.review.addItems(["Accepted", "Review before use", "Excluded"])
        self.include = QCheckBox("Use this point in the calculation")
        self.include.setChecked(True)
        self.notes = QLineEdit()

        form.addRow("Taxon", self.scientific_name)
        if show_coordinates:
            form.addRow("Decimal latitude*", self.latitude)
            form.addRow("Decimal longitude*", self.longitude)
        form.addRow("Date", self.event_date)
        form.addRow("Data source", self.data_origin_text)
        form.addRow("Data curator", self.data_curator)
        form.addRow("Evidence", self.evidence)
        form.addRow("Identifier (voucher number or other ID)", self.identifier)
        form.addRow("Uncertainty", self.uncertainty)
        form.addRow("Decision for this point", self.review)
        form.addRow("Calculation", self.include)
        form.addRow("Notes", self.notes)
        layout.addLayout(form)

        buttons = QDialogButtonBox(_button_box_ok() | _button_box_cancel())
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def values(self) -> dict:
        review_map = {
            "Review before use": "revisar",
            "Accepted": "aceptado",
            "Excluded": "excluido",
        }
        data_citation = ""
        data_origin = self.data_origin_text.text().strip() or "manual"
        values = {
            "scientificName": self.scientific_name.text().strip(),
            "eventDate": self.event_date.text().strip(),
            "data_citation": data_citation,
            "observer": data_citation,  # compatibility with older temporary layers
            "source_ref": data_citation,
            "data_origin": data_origin,
            "data_curator": self.data_curator.text().strip(),
            "evidence": self.evidence.currentText(),
            "identifier": self.identifier.text().strip(),
            "catalog_no": self.identifier.text().strip(),
            "coordUncM": self.uncertainty.value(),
            "review": review_map.get(self.review.currentText(), "revisar"),
            "include": self.include.isChecked(),
            "notes": self.notes.text().strip(),
        }
        if self.show_coordinates:
            values["decimalLatitude"] = self.latitude.value()
            values["decimalLongitude"] = self.longitude.value()
        return values



class PointDistributionSettingsDialog(QDialog):
    """Form with shared fields for the IUCN Point Distribution CSV."""

    def __init__(self, parent=None, default_name: str = "", default_subspecies: str = ""):
        super().__init__(parent)
        self.setWindowTitle("Point Distribution CSV settings")
        self.resize(720, 620)
        layout = QVBoxLayout(self)
        intro = QLabel(
            "These values will be applied to the Point Distribution CSV rows. "
            "The dec_lat and dec_long coordinates are filled automatically from the points used in the calculation. "
            "The file will follow exactly the column schema you provided."
        )
        intro.setWordWrap(True)
        layout.addWidget(intro)

        form = QFormLayout()
        this_year = datetime.now().year
        self.sci_name = QLineEdit(default_name)

        self.presence = QComboBox()
        self.presence.addItem("1 - Extant", 1)
        self.presence.addItem("3 - Possibly Extant", 3)
        self.presence.addItem("4 - Possibly Extinct", 4)
        self.presence.addItem("5 - Extinct", 5)
        self.presence.addItem("6 - Presence Uncertain", 6)
        self.presence.addItem("7 - Extant & Introduced", 7)

        self.origin = QComboBox()
        self.origin.addItem("1 - Native", 1)
        self.origin.addItem("2 - Reintroduced", 2)
        self.origin.addItem("3 - Introduced", 3)
        self.origin.addItem("4 - Vagrant", 4)
        self.origin.addItem("5 - Origin Uncertain", 5)
        self.origin.addItem("6 - Assisted Colonisation", 6)
        self.origin.addItem("7 - Origin Uncertain or Mixed", 7)

        self.seasonal = QComboBox()
        self.seasonal.addItem("1 - Resident", 1)
        self.seasonal.addItem("2 - Breeding Season", 2)
        self.seasonal.addItem("3 - Non-breeding Season", 3)
        self.seasonal.addItem("4 - Passage", 4)
        self.seasonal.addItem("5 - Seasonal Occurrence Uncertain", 5)

        self.compiler = QLineEdit()
        self.yrcompiled = QSpinBox()
        self.yrcompiled.setRange(1900, this_year + 1)
        self.yrcompiled.setValue(this_year)
        self.citation = QLineEdit()
        self.spatialref = QLineEdit("WGS84")
        self.subspecies = QLineEdit(default_subspecies)
        self.subpop = QLineEdit()

        self.data_sens = QComboBox()
        self.data_sens.addItem("0 - Not sensitive", 0)
        self.data_sens.addItem("1 - Sensitive", 1)

        self.sens_comm = QLineEdit()
        self.source = QLineEdit("GBIF.org and reviewed user data")
        self.basisofrec = QLineEdit()
        self.dist_comm = QLineEdit()
        self.island = QLineEdit()
        self.tax_comm = QLineEdit()

        form.addRow("sci_name *", self.sci_name)
        form.addRow("presence *", self.presence)
        form.addRow("origin *", self.origin)
        form.addRow("seasonal", self.seasonal)
        form.addRow("compiler *", self.compiler)
        form.addRow("yrcompiled *", self.yrcompiled)
        form.addRow("citation *", self.citation)
        form.addRow("spatialref *", self.spatialref)
        form.addRow("subspecies", self.subspecies)
        form.addRow("subpop", self.subpop)
        form.addRow("data_sens", self.data_sens)
        form.addRow("sens_comm", self.sens_comm)
        form.addRow("source", self.source)
        form.addRow("basisofrec", self.basisofrec)
        form.addRow("dist_comm", self.dist_comm)
        form.addRow("island", self.island)
        form.addRow("tax_comm", self.tax_comm)
        layout.addLayout(form)

        note = QLabel(
            "* Required or core fields for Point Distribution following the IUCN template. "
            "If data_sens = 1, fill in sens_comm. "
            "event_year is completed from the record date/year when available. "
            "catalog_no is filled with gbifID for GBIF records."
        )
        note.setWordWrap(True)
        layout.addWidget(note)

        buttons = QDialogButtonBox(_button_box_ok() | _button_box_cancel())
        buttons.accepted.connect(self._validate_and_accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _validate_and_accept(self):
        missing = []
        if not self.sci_name.text().strip():
            missing.append("sci_name")
        if not self.compiler.text().strip():
            missing.append("compiler")
        if not self.citation.text().strip():
            missing.append("citation")
        if not self.spatialref.text().strip():
            missing.append("spatialref")
        if self.data_sens.currentData() == 1 and not self.sens_comm.text().strip():
            missing.append("sens_comm because data_sens=1")
        if missing:
            QMessageBox.warning(self, "Point Distribution", "Missing fields: " + ", ".join(missing))
            return
        self.accept()

    def values(self) -> dict:
        return {
            "sci_name": self.sci_name.text().strip(),
            "presence": self.presence.currentData(),
            "origin": self.origin.currentData(),
            "seasonal": self.seasonal.currentData(),
            "compiler": self.compiler.text().strip(),
            "yrcompiled": self.yrcompiled.value(),
            "citation": self.citation.text().strip(),
            "spatialref": self.spatialref.text().strip() or "WGS84",
            "subspecies": self.subspecies.text().strip(),
            "subpop": self.subpop.text().strip(),
            "data_sens": self.data_sens.currentData(),
            "sens_comm": self.sens_comm.text().strip(),
            "source": self.source.text().strip(),
            "basisofrec": self.basisofrec.text().strip(),
            "dist_comm": self.dist_comm.text().strip(),
            "island": self.island.text().strip(),
            "tax_comm": self.tax_comm.text().strip(),
        }


POINT_DISTRIBUTION_HELP = [
    ("sci_name", "Scientific name of the taxon. It must match the name used in the assessment."),
    ("presence", "IUCN presence code. Usually 1 = extant."),
    ("origin", "IUCN origin code. Usually 1 = native."),
    ("seasonal", "IUCN seasonal code. In plants this is usually 1 = resident, unless another case applies."),
    ("compiler", "Person or institution compiling the point file."),
    ("yrcompiled", "Year when the file is compiled or modified."),
    ("citation", "Overall credit for the distribution file. It should remain the same throughout the file."),
    ("dec_lat", "Decimal latitude of the point. The plugin fills it from the points used."),
    ("dec_long", "Decimal longitude of the point. The plugin fills it from the points used."),
    ("spatialref", "Coordinate reference system. Default is WGS84."),
    ("subspecies", "Infraspecific epithet if a subspecies or variety is being assessed."),
    ("subpop", "Subpopulation name, if applicable. Kept because it is part of the Point Distribution template."),
    ("data_sens", "0 = not sensitive; 1 = sensitive."),
    ("sens_comm", "Reason why the data are sensitive. Must be completed if data_sens = 1."),
    ("event_year", "Year of observation or collection, if available. The plugin tries to recover it from the record."),
    ("source", "Primary source of the point: GBIF, fieldwork, herbarium, report, publication, etc."),
    ("basisofrec", "Nature of the record, for example PreservedSpecimen or HumanObservation."),
    ("catalog_no", "Record identifier. For GBIF it is filled with gbifID when available."),
    ("dist_comm", "Distribution comment associated with the point."),
    ("island", "Island, if applicable."),
    ("tax_comm", "Taxonomic comment associated with the point."),
]


class PointDistributionHelpDialog(QDialog):
    """Scrollable help for the exact Point Distribution CSV schema."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Point Distribution field guide")
        self.resize(820, 620)
        layout = QVBoxLayout(self)
        intro = QLabel(
            "The Point Distribution table is generated with the exact schema provided: "
            "21 fields, in the same order, with no extra columns added."
        )
        intro.setWordWrap(True)
        layout.addWidget(intro)

        text = QTextEdit()
        text.setReadOnly(True)
        text.setMinimumHeight(480)
        lines = ["Campos exportados, en orden exacto:\n"]
        for idx, (field, definition) in enumerate(POINT_DISTRIBUTION_HELP, start=1):
            lines.append(f"{idx:02d}. {field}\n    {definition}\n")
        lines.append(
            "\nNote: dec_lat and dec_long are not filled in the dialog because the plugin "
            "takes them automatically from the points used in the last calculation. catalog_no is filled "
            "with gbifID when the record comes from GBIF."
        )
        text.setPlainText("\n".join(lines))
        layout.addWidget(text)

        buttons = QDialogButtonBox(_button_box_ok())
        buttons.accepted.connect(self.accept)
        layout.addWidget(buttons)



COORDINATECLEANER_CRITERIOS_ES = [
    ("missing coordinates", "Records without usable latitude or longitude."),
    ("coordinates out of range", "Records with latitude outside -90/90 or longitude outside -180/180."),
    ("0,0 coordinates", "Records located exactly at point 0,0."),
    ("longitude equal to latitude", "Records where latitude and longitude are exactly the same."),
    ("GBIF issue: zero coordinate", "Records that GBIF already flags with a zero-coordinate issue."),
    ("GBIF issue: possible country centroid", "Records that GBIF already flags as a possible country centroid."),
    ("GBIF issue: invalid coordinate", "Records that GBIF flags as an invalid coordinate."),
    ("GBIF issue: coordinate out of range", "Records that GBIF flags as out of range."),
    ("GBIF headquarters", "Coordinates matching GBIF headquarters or the Copenhagen area."),
    ("capital coordinates", "Coordinates that match almost exactly some capital cities."),
    ("country centroids", "Coordinates that match almost exactly national centroids or very generic values."),
    ("institution coordinates", "Coordinates that match almost exactly some botanical institutions or museums."),
]

COORDINATECLEANER_REASON_TRANSLATION = {
    "coordenadas ausentes": "missing coordinates",
    "coordenadas fuera de rango": "coordinates out of range",
    "coordenadas 0,0": "coordinates 0,0",
    "longitud igual a latitud": "longitud igual a latitud",
    "GBIF issue ZERO_COORDINATE": "problema GBIF: coordenada cero",
    "GBIF issue COUNTRY_CENTROID": "GBIF issue: possible country centroid",
    "GBIF issue COORDINATE_INVALID": "GBIF issue: invalid coordinate",
    "GBIF issue COORDINATE_OUT_OF_RANGE": "problema GBIF: coordenada fuera de rango",
    "gbif_headquarters": "sede de GBIF",
    "capital_coordinates": "capital coordinates",
    "country_centroids": "country centroids",
    "institution_coordinates": "institution coordinates",
}

class AooEooDialog(QDialog):
    """Main non-modal plugin dialog."""

    def __init__(self, iface, parent=None):
        super().__init__(parent or iface.mainWindow())
        self.iface = iface
        self.manual_layer = None
        self.manual_layer_id = None
        self.gbif_layer = None
        self.gbif_layer_id = None
        self.manual_tool = None
        self.previous_map_tool = None
        self.last_result = None
        self.point_distribution_layer = None
        self.gbif_doi_layer = None
        self.gbif_download_key = ""
        self.gbif_download_response = None
        self.calc_layers_list = None

        self.last_filter_removed = []
        self.setWindowTitle("IUCN Red List calculator")
        self.resize(900, 740)
        self.setMinimumSize(760, 560)
        self._build_ui()
        # Both objects are constructed in _build_ui; failure to connect is a
        # genuine UI initialization error and must not be silently ignored.
        self.tabs.currentChanged.connect(self._on_tab_changed)
        # The calculation layer list is not auto-populated from the whole project on startup,
        # because old project layers can otherwise appear as default data.
        # It is refreshed by user action or when the plugin itself creates/imports layers.

    # ------------------------------------------------------------------ UI
    def _build_ui(self):
        main = QVBoxLayout(self)
        intro = QLabel(
            "EN: Tool to calculate AOO and EOO from GBIF records and, if needed, from user points. "
            "Before using the results in a formal assessment, review isolated points, coordinate precision and the source of each record. "
            "If the query returns a very high number of records, download and calculation may take longer and may slow down QGIS.\n\n"
            "ES: Herramienta para calcular AOO y EOO a partir de registros de GBIF y, si es necesario, de puntos propios. "
            "Antes de usar los resultados en una evaluación formal, revisa los puntos aislados, la precisión de las coordenadas y la fuente de cada dato. "
            "Si la consulta devuelve un número muy alto de registros, la descarga y el cálculo pueden tardar más tiempo y ralentizar QGIS."
        )
        intro.setWordWrap(True)
        main.addWidget(intro)

        self.tabs = QTabWidget()
        self.tabs.setUsesScrollButtons(True)
        self.tabs.addTab(self._make_gbif_tab(), "1. GBIF and filters")
        self.tabs.addTab(self._make_data_tab(), "2. Layers and user points")
        self.tabs.addTab(self._make_calc_tab(), "3. Calculate AOO/EOO")
        self.tabs.addTab(self._make_report_tab(), "4. Point Distribution")
        self.tabs.addTab(self._make_gbif_citation_tab(), "5. GBIF citation / DOI")
        main.addWidget(self.tabs)

        self.log = QTextEdit()
        self.log.setReadOnly(True)
        self.log.setMinimumHeight(110)
        self.log.setMaximumHeight(160)
        main.addWidget(self.log)

        close_button = QPushButton("Close")
        close_button.clicked.connect(self.close)
        bottom = QHBoxLayout()
        bottom.addStretch(1)
        bottom.addWidget(close_button)
        main.addLayout(bottom)

    def _make_gbif_tab(self) -> QWidget:
        tab = QWidget()
        layout = QVBoxLayout(tab)

        form_box = QGroupBox("GBIF search")
        form = QGridLayout(form_box)
        form.setColumnStretch(1, 1)
        form.setColumnStretch(3, 1)

        def etiqueta(texto: str, ayuda: str) -> QLabel:
            label = QLabel(texto)
            label.setToolTip(ayuda)
            return label

        self.scientific_name = QLineEdit()
        self.scientific_name.setPlaceholderText("E.g.: Genista sanabrensis; or full infraspecific name")
        # Al pulsar Enter desde el campo de nombre científico, resolver el taxonKey.
        # Evita que Qt active por defecto otro botón de la pestaña, como la tabla de criterios.
        self.scientific_name.returnPressed.connect(self.resolve_taxon)
        self.assess_infraspecific = QCheckBox("Evaluar como subespecie o variedad")
        self.assess_infraspecific.setChecked(False)
        self.infraspecific_epithet = QLineEdit()
        self.infraspecific_epithet.setPlaceholderText("Infraspecific epithet, e.g. brevifolia; optional")
        self.taxon_key = QLineEdit()
        self.taxon_key.setPlaceholderText("Optional; can be resolved from the name")
        self.country_code = QLineEdit()
        self.country_code.setMaxLength(2)
        self.country_code.setPlaceholderText("ES, PT, FR... optional")

        this_year = datetime.now().year
        self.year_min = QSpinBox()
        self.year_min.setRange(0, this_year + 1)
        self.year_min.setSpecialValueText("no minimum")
        self.year_min.setValue(0)
        self.year_max = QSpinBox()
        self.year_max.setRange(0, this_year + 1)
        self.year_max.setSpecialValueText("no maximum")
        self.year_max.setValue(0)
        self.scientific_name.setToolTip(
            "Scientific name to search in GBIF. It can be a species or a full infraspecific name. Example: Genista sanabrensis.\nES: Nombre científico que se buscará en GBIF. Puede ser especie o nombre infraespecífico completo. Ejemplo: Genista sanabrensis."
        )
        self.assess_infraspecific.setToolTip(
            "Check this when the assessment is for a subspecies or variety. The infraspecific epithet will later be used in the IUCN/SRedList outputs.\nES: Márcalo cuando la evaluación sea para una subespecie o variedad. El epíteto infraespecífico se usará después en las salidas IUCN/SRedList."
        )
        self.infraspecific_epithet.setToolTip(
            "Infraspecific epithet, without repeating the genus or species. Example: brevifolia.\nES: Epíteto infraespecífico, sin repetir el género ni la especie. Ejemplo: brevifolia."
        )
        self.taxon_key.setToolTip(
            "Numeric GBIF identifier for the taxon. Optional: you can resolve it from the scientific name using the Resolve taxonKey button.\nES: Identificador numérico de GBIF para el taxón. Es opcional: puedes resolverlo desde el nombre científico con el botón Resolver taxonKey."
        )
        self.country_code.setToolTip(
            "Two-letter ISO code to restrict the search by country. Examples: ES, PT, FR. Leave empty to avoid filtering by country.\nES: Código ISO de dos letras para limitar la búsqueda por país. Ejemplos: ES, PT, FR. Déjalo vacío para no filtrar por país."
        )
        self.year_min.setToolTip(
            "Minimum GBIF record year. Records earlier than this year will be removed from the download and documented in the removed-records table. Use 'no minimum' to disable this filter.\nES: Año mínimo del registro GBIF. Se eliminarán de la descarga los registros anteriores a este año y quedarán documentados en la tabla de registros eliminados. Usa 'sin mínimo' para no aplicar este filtro."
        )
        self.year_max.setToolTip(
            "Maximum GBIF record year. Records later than this year will be removed from the download and documented in the removed-records table. Use 'no maximum' to disable this filter.\nES: Año máximo del registro GBIF. Se eliminarán de la descarga los registros posteriores a este año y quedarán documentados en la tabla de registros eliminados. Usa 'sin máximo' para no aplicar este filtro."
        )
        self.exclude_geospatial_issues = QCheckBox("hasGeospatialIssue = false")
        self.exclude_geospatial_issues.setChecked(True)
        self.exclude_geospatial_issues.setToolTip(
            "When checked, GBIF returns only records without known general geospatial issues. It is recommended to keep it enabled.\nES: Cuando está marcado, GBIF devuelve solo registros sin incidencias geoespaciales generales conocidas. Es recomendable dejarlo activado."
        )
        self.has_coordinate = QCheckBox("hasCoordinate = true")
        self.has_coordinate.setChecked(True)
        self.has_coordinate.setEnabled(False)
        self.has_coordinate.setToolTip(
            "Requires records to have coordinates. This is necessary to calculate AOO, EOO and generate point outputs.\nES: Obliga a que los registros tengan coordenadas. Es necesario para calcular AOO, EOO y generar puntos."
        )

        self.occurrence_status = QComboBox()
        self.occurrence_status.addItems(["PRESENT", "ABSENT", "no filtrar"])
        self.occurrence_status.setCurrentText("PRESENT")
        self.occurrence_status.setToolTip("Occurrence status in GBIF. For distribution and threat assessment this should normally be PRESENT. ABSENT is not used for AOO/EOO.\nES: Estado de ocurrencia en GBIF. Para distribución y evaluación de amenaza normalmente debe ser PRESENT. ABSENT no se usa para AOO/EOO.")

        self.synonym_1 = QLineEdit()
        self.synonym_1.setPlaceholderText("Synonym 1, optional")
        self.synonym_2 = QLineEdit()
        self.synonym_2.setPlaceholderText("Synonym 2, optional")
        self.synonym_3 = QLineEdit()
        self.synonym_3.setPlaceholderText("Synonym 3, optional")
        self.synonym_4 = QLineEdit()
        self.synonym_4.setPlaceholderText("Synonym 4, optional")
        for syn_widget in [self.synonym_1, self.synonym_2, self.synonym_3, self.synonym_4]:
            syn_widget.setToolTip(
                "Alternative name or synonym that will also be queried in GBIF. Use it only when you want to include records published under another name.\nES: Nombre alternativo o sinónimo que también se consultará en GBIF. Úsalo solo cuando quieras sumar registros publicados bajo otro nombre."
            )

        self.coordinatecleaner_filter = QCheckBox("Apply automatic CoordinateCleaner-like filter")
        self.coordinatecleaner_filter.setChecked(True)
        cc_text = (
            "Enabled by default. Filter inspired by CoordinateCleaner (Zizka et al. 2019), as in SRedList: it can be disabled and flags records with coordinates matching capitals, country centroids, GBIF headquarters, some institutions, or equal longitude and latitude. In this plugin a conservative Python version is applied before creating the GBIF layer.\nES: Marcado por defecto. Filtro inspirado en CoordinateCleaner (Zizka et al. 2019), como en SRedList: puede desactivarse y señala registros con coordenadas coincidentes con capitales, centroides de país, la sede de GBIF, algunas instituciones o con longitud igual a latitud. En este plugin se aplica una versión Python conservadora antes de crear la capa GBIF."
        )
        self.coordinatecleaner_filter.setToolTip(cc_text)
        self.show_cc_criteria_button = QPushButton("View filter criteria")
        self.show_cc_criteria_button.setToolTip("Show the exact criteria and reasons applied by the CoordinateCleaner-like filter.\nES: Muestra los criterios exactos y los motivos aplicados por el filtro tipo CoordinateCleaner.")
        self.show_cc_criteria_button.setToolTip("Create a table listing the specific reasons applied by the CoordinateCleaner-like filter.\nES: Crea una tabla con los motivos concretos que puede aplicar el filtro tipo CoordinateCleaner.")
        self.show_cc_criteria_button.clicked.connect(self.create_coordinatecleaner_criteria_table)
        self.show_cc_criteria_button.setAutoDefault(False)
        self.show_cc_criteria_button.setDefault(False)

        self.gbif_uncertainty_filter = QCheckBox("Filter by coordinate uncertainty")
        self.gbif_uncertainty_filter.setChecked(False)
        self.gbif_uncertainty_filter.setToolTip(
            "Enable this filter if you want to remove GBIF records whose spatial uncertainty is larger than the given threshold. The threshold is interpreted in metres. Records with no uncertainty value are kept for review.\nES: Activa este filtro si quieres retirar registros de GBIF cuya incertidumbre espacial sea mayor que el umbral indicado. El umbral se interpreta en metros. Los registros sin valor de incertidumbre se mantienen para revisión."
        )
        self.gbif_uncertainty_combo = QComboBox()
        self.gbif_uncertainty_combo.setEditable(True)
        self.gbif_uncertainty_combo.setToolTip(
            "Select a value from the drop-down list or type your own. Units are not mandatory: 7050 is interpreted as 7050 metres. You can also write 7050 m or 7.05 km.\nES: Selecciona un valor del desplegable o escribe uno propio. No es obligatorio escribir unidades: 7050 se interpreta como 7050 metros. También puedes escribir 7050 m o 7.05 km."
        )
        for label, value in [
            ("100 m", 100),
            ("250 m", 250),
            ("500 m", 500),
            ("1 km", 1000),
            ("2 km", 2000),
            ("5 km", 5000),
            ("10 km", 10000),
            ("No limit", None),
        ]:
            self.gbif_uncertainty_combo.addItem(label, value)
        self.gbif_uncertainty_combo.setCurrentText("1 km")

        form.addWidget(etiqueta("Scientific name", "Scientific name to be searched in GBIF. It can be a species or a full infraspecific name.\nES: Nombre del taxón que se buscará en GBIF. Puede ser especie o nombre infraespecífico completo."), 0, 0)
        form.addWidget(self.scientific_name, 0, 1)
        form.addWidget(etiqueta("taxonKey", "Numeric GBIF identifier. Optional and can be resolved from the scientific name.\nES: Identificador numérico de GBIF. Es opcional y puede resolverse desde el nombre científico."), 0, 2)
        form.addWidget(self.taxon_key, 0, 3)
        form.addWidget(self.assess_infraspecific, 1, 0)
        form.addWidget(self.infraspecific_epithet, 1, 1)
        form.addWidget(etiqueta("Country", "Two-letter ISO code to filter by country, for example ES. Leave empty to avoid filtering.\nES: Código ISO de dos letras para filtrar por país, por ejemplo ES. Déjalo vacío para no filtrar."), 1, 2)
        form.addWidget(self.country_code, 1, 3)
        form.addWidget(etiqueta("Minimum year", "Minimum GBIF record year. Earlier records will be removed and can be reviewed in the removed-records table.\nES: Año mínimo del registro GBIF. Los registros anteriores se retirarán y se podrán ver en la tabla de registros eliminados."), 2, 0)
        form.addWidget(self.year_min, 2, 1)
        form.addWidget(etiqueta("Maximum year", "Maximum GBIF record year. Later records will be removed and can be reviewed in the removed-records table.\nES: Año máximo del registro GBIF. Los registros posteriores se retirarán y se podrán ver en la tabla de registros eliminados."), 2, 2)
        form.addWidget(self.year_max, 2, 3)
        form.addWidget(etiqueta("Occurrence status", "PRESENT includes presence records. ABSENT should not be used to calculate AOO/EOO except under very specific review.\nES: PRESENT incluye registros de presencia. ABSENT no debe usarse para calcular AOO/EOO salvo revisión muy específica."), 3, 0)
        form.addWidget(self.occurrence_status, 3, 1)
        form.addWidget(self.has_coordinate, 4, 0)
        form.addWidget(self.exclude_geospatial_issues, 4, 1)
        form.addWidget(self.coordinatecleaner_filter, 5, 0, 1, 2)
        form.addWidget(self.show_cc_criteria_button, 5, 2, 1, 2)
        form.addWidget(self.gbif_uncertainty_filter, 6, 0, 1, 2)
        umbral_incertidumbre_label = QLabel("Uncertainty threshold (m)")
        umbral_incertidumbre_label.setToolTip(
            "Maximum accepted coordinate uncertainty. If you type only a number, it is interpreted in metres. Example: 7050 = 7050 m.\nES: Valor máximo aceptado de incertidumbre de coordenadas. Si escribes solo un número, se interpreta en metros. Ejemplo: 7050 = 7050 m."
        )
        form.addWidget(umbral_incertidumbre_label, 6, 2)
        form.addWidget(self.gbif_uncertainty_combo, 6, 3)
        form.addWidget(etiqueta("Optional synonyms", "Alternative names that will also be queried in GBIF. Use them to include records published under synonyms.\nES: Nombres alternativos que también se consultarán en GBIF. Úsalos para incluir registros publicados bajo sinónimos."), 7, 0)
        form.addWidget(self.synonym_1, 7, 1)
        form.addWidget(self.synonym_2, 7, 2)
        form.addWidget(self.synonym_3, 8, 1)
        form.addWidget(self.synonym_4, 8, 2)
        layout.addWidget(form_box)

        filters = QHBoxLayout()
        self.basis_list = self._make_check_list(BASIS_OPTIONS)
        self.basis_list.setToolTip(
            "Record type in GBIF. For plants, HUMAN_OBSERVATION and PRESERVED_SPECIMEN are often useful. MACHINE_OBSERVATION is unchecked by default.\nES: Tipo de registro en GBIF. Para plantas suelen ser útiles HUMAN_OBSERVATION y PRESERVED_SPECIMEN. MACHINE_OBSERVATION queda desmarcado por defecto."
        )
        basis_box = QGroupBox("basisOfRecord")
        basis_box.setToolTip(
            "Nature of the record: human observation, preserved specimen, machine observation, sample, etc.\nES: Naturaleza del registro: observación humana, pliego conservado, observación de máquina, muestra, etc."
        )
        basis_layout = QVBoxLayout(basis_box)
        basis_layout.addWidget(self.basis_list)
        filters.addWidget(basis_box)

        self.establishment_list = self._make_check_list(ESTABLISHMENT_OPTIONS)
        self.establishment_list.setToolTip(
            "Origin or establishment means of the record according to GBIF: native, introduced, reintroduced, uncertain, etc.\nES: Origen o forma de establecimiento del registro según GBIF: nativo, introducido, reintroducido, incierto, etc."
        )
        est_box = QGroupBox("establishmentMeans")
        est_box.setToolTip(
            "Allows filtering by origin of the taxon. For native-distribution assessments, this is usually reviewed carefully.\nES: Permite filtrar por origen del taxón. Para evaluaciones de distribución nativa, suele revisarse con cuidado."
        )
        est_layout = QVBoxLayout(est_box)
        est_layout.addWidget(self.establishment_list)
        self.filter_establishment = QCheckBox("Apply this filter")
        self.filter_establishment.setChecked(False)
        self.filter_establishment.setToolTip(
            "If unchecked, the selected establishmentMeans values are not used to filter. Check it only if you want to restrict records by origin.\nES: Si no está marcado, los valores seleccionados de establishmentMeans no se usan para filtrar. Márcalo solo si quieres restringir los registros por origen."
        )
        est_layout.addWidget(self.filter_establishment)
        filters.addWidget(est_box)
        layout.addLayout(filters)

        buttons = QHBoxLayout()
        self.resolve_button = QPushButton("Resolve taxonKey")
        self.resolve_button.setToolTip("Resolve the GBIF taxonKey from the scientific name.\nES: Resuelve el taxonKey de GBIF a partir del nombre científico indicado.")
        self.resolve_button.setToolTip("Resolve the GBIF taxonKey from the scientific name.\nES: Resuelve el taxonKey de GBIF a partir del nombre científico.")
        self.resolve_button.clicked.connect(self.resolve_taxon)
        self.preview_button = QPushButton("Preview GBIF counts")
        self.preview_button.setToolTip("Consulta conteos/facetas de GBIF antes de descargar los registros completos.")
        self.preview_button.setToolTip("Preview GBIF counts and facets before downloading full records.\nES: Previsualiza los conteos y facetas de GBIF antes de descargar los registros completos.")
        self.preview_button.clicked.connect(self.preview_facets)
        self.download_button = QPushButton("Download GBIF occurrences")
        self.download_button.setToolTip("Download records from GBIF using the filters set in this tab.\nES: Descarga registros de GBIF usando los filtros indicados en esta pestaña.")
        self.download_button.clicked.connect(self.download_gbif)
        self.reset_gbif_button = QPushButton("Reset")
        self.reset_gbif_button.setToolTip("Clear the fields and restore this tab filters to their initial values.\nES: Limpia los campos y devuelve los filtros de esta pestaña a sus valores iniciales.")
        self.reset_gbif_button.clicked.connect(self.reset_gbif_tab)
        self.show_filtered_button = QPushButton("View removed records")
        self.show_filtered_button.setToolTip("Create a table with the records removed by the filters applied in the last GBIF download.\nES: Crea una tabla con los registros retirados por los filtros aplicados en la última descarga GBIF.")
        self.show_filtered_button.clicked.connect(self.create_filtered_records_table)
        for _boton_gbif in [
            self.resolve_button,
            self.preview_button,
            self.download_button,
            self.reset_gbif_button,
            self.show_filtered_button,
        ]:
            _boton_gbif.setAutoDefault(False)
            _boton_gbif.setDefault(False)
        buttons.addWidget(self.resolve_button)
        buttons.addWidget(self.preview_button)
        buttons.addWidget(self.reset_gbif_button)
        buttons.addWidget(self.show_filtered_button)
        buttons.addStretch(1)
        buttons.addWidget(self.download_button)
        layout.addLayout(buttons)
        layout.addStretch(1)
        return tab

    def _make_data_tab(self) -> QWidget:
        tab = QWidget()
        layout = QVBoxLayout(tab)

        self.layer_combo = None  # compatibilidad interna: la selección de capas se hace en la pestaña 3

        manual_box = QGroupBox("User-added points")
        manual_layout = QVBoxLayout(manual_box)
        self.manual_status = QLabel("You have not created a layer for your user points yet.")
        manual_layout.addWidget(self.manual_status)
        manual_buttons = QGridLayout()
        self.create_manual_button = QPushButton("Create layer for my points")
        self.create_manual_button.clicked.connect(self.create_manual_points_layer)
        self.activate_manual_button = QPushButton("Add point by clicking on the map")
        self.activate_manual_button.setToolTip("Activate a map tool to add user points by clicking on the map canvas.\nES: Activa una herramienta de mapa para añadir puntos propios haciendo clic en el mapa.")
        self.activate_manual_button.clicked.connect(self.activate_manual_point_tool)
        self.add_manual_coordinates_button = QPushButton("Add point by entering coordinates")
        self.add_manual_coordinates_button.setToolTip("Open a form to add a point by decimal coordinates.\nES: Abre un formulario para añadir un punto mediante coordenadas decimales.")
        self.add_manual_coordinates_button.clicked.connect(self.add_manual_point_by_coordinates)
        self.stop_manual_button = QPushButton("Stop adding points")
        self.stop_manual_button.setToolTip("Stop the current point-adding mode.\nES: Detiene el modo actual de adición de puntos.")
        self.stop_manual_button.clicked.connect(self.stop_manual_point_tool)
        self.import_csv_button = QPushButton("Import my points from CSV")
        self.import_csv_button.setToolTip("Import CSV points as a new, independent layer. Each imported file remains separate from points added manually.\nES: Importa el CSV en una capa nueva e independiente, separada de los puntos introducidos manualmente.")
        self.import_csv_button.clicked.connect(self.import_manual_points_csv)
        self.import_shapefile_button = QPushButton("Import points from shapefile")
        self.import_shapefile_button.setToolTip("Load a point shapefile into the QGIS project and mark it so it can be used directly in the tab 3 calculation. Its original attribute table is preserved.\nES: Carga un shapefile de puntos en el proyecto de QGIS y lo marca para poder usarlo directamente en el cálculo de la pestaña 3. Se conserva su tabla de atributos original.")
        self.import_shapefile_button.clicked.connect(self.import_point_shapefile)
        self.save_csv_template_button = QPushButton("Save base CSV template")
        self.save_csv_template_button.setToolTip("Save a base CSV template compatible with the plugin.\nES: Guarda una plantilla base CSV compatible con el plugin.")
        self.save_csv_template_button.clicked.connect(self.save_manual_csv_template)
        manual_buttons.addWidget(self.create_manual_button, 0, 0)
        manual_buttons.addWidget(self.activate_manual_button, 0, 1)
        manual_buttons.addWidget(self.add_manual_coordinates_button, 1, 0)
        manual_buttons.addWidget(self.import_csv_button, 1, 1)
        manual_buttons.addWidget(self.import_shapefile_button, 2, 0, 1, 2)
        manual_buttons.addWidget(self.save_csv_template_button, 3, 0, 1, 2)
        manual_buttons.addWidget(self.stop_manual_button, 4, 0, 1, 2)
        manual_layout.addLayout(manual_buttons)
        hint = QLabel(
            "EN: Points added by clicking or entering coordinates use the manual layer; each imported CSV becomes a new independent layer. "
            "You can also import a point shapefile as an independent QGIS layer, preserving its original attribute table. "
            "If you need to delete or correct points, edit the layer directly in QGIS and then calculate from the checked layers in tab 3. "
            "Manual points must be marked for use; CSV records without an explicit include/review value are accepted by default, while explicit exclusions are preserved. CSV import accepts latitude as decimalLatitude, latitude, lat or dec_lat, and longitude as decimalLongitude, longitude, lon, lng, dec_lon, dec_long or long.\n\n"
            "ES: Los puntos añadidos haciendo clic o introduciendo coordenadas van a la capa manual; cada CSV importado crea una capa independiente. "
            "También puedes importar un shapefile de puntos como capa independiente de QGIS, conservando su tabla de atributos original. "
            "Si necesitas borrar o corregir puntos, edita directamente la capa en QGIS y después calcula con las capas marcadas en la pestaña 3. "
            "Los puntos manuales deben marcarse para el cálculo. Los CSV sin valores explícitos de inclusión/revisión se aceptan por defecto; se respetan las exclusiones explícitas. Para CSV se acepta latitud como decimalLatitude, latitude, lat o dec_lat, y longitud como decimalLongitude, longitude, lon, lng, dec_lon, dec_long o long."
        )
        hint.setWordWrap(True)
        manual_layout.addWidget(hint)
        layout.addWidget(manual_box)
        layout.addStretch(1)
        return tab

    def _make_calc_tab(self) -> QWidget:
        tab = QWidget()
        outer = QVBoxLayout(tab)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        content = QWidget()
        layout = QVBoxLayout(content)

        layers_box = QGroupBox("Layers to use in the calculation")
        layers_layout = QVBoxLayout(layers_box)
        layers_hint = QLabel(
            "EN: Check one or more point layers in the project. The calculation will use only the checked layers. "
            "This allows AOO/EOO to be calculated from GBIF, imported CSV, user points, any point layer loaded in QGIS, or several combined layers.\n\n"
            "ES: Marca una o varias capas de puntos del proyecto. El cálculo usará solo las capas marcadas. "
            "Esto permite calcular AOO/EOO desde GBIF, CSV importado, puntos propios, cualquier capa de puntos cargada en QGIS o varias capas combinadas."
        )
        layers_hint.setWordWrap(True)
        layers_layout.addWidget(layers_hint)
        self.calc_layers_list = QListWidget()
        self.calc_layers_list.setMinimumHeight(150)
        # QListWidget supports this selection mode in supported Qt versions.
        self.calc_layers_list.setSelectionMode(QAbstractItemView.MultiSelection)
        layers_layout.addWidget(self.calc_layers_list)
        self.calc_selection_summary = QLabel("Selected for calculation / Capas seleccionadas: none / ninguna")
        self.calc_selection_summary.setWordWrap(True)
        layers_layout.addWidget(self.calc_selection_summary)
        self.calc_layers_list.itemChanged.connect(self._update_calc_selection_summary)
        layer_buttons = QGridLayout()
        self.refresh_calc_layers_button = QPushButton("Refresh layer list")
        self.refresh_calc_layers_button.setToolTip("Refresh the list of point layers available in the current QGIS project.\nES: Actualiza la lista de capas de puntos disponibles en el proyecto actual de QGIS.")
        self.refresh_calc_layers_button.clicked.connect(lambda: self.refresh_calc_layers(apply_defaults=False))
        self.check_current_layer_button = QPushButton("Check active layer")
        self.check_current_layer_button.setToolTip("Check the currently active point layer.\nES: Marca la capa de puntos activa en este momento.")
        self.check_current_layer_button.clicked.connect(self.check_current_calc_layer)
        self.check_all_layers_button = QPushButton("Check all")
        self.check_all_layers_button.setToolTip("Check all available point layers.\nES: Marca todas las capas de puntos disponibles.")
        self.check_all_layers_button.clicked.connect(self.check_all_calc_layers)
        self.uncheck_all_layers_button = QPushButton("Uncheck all")
        self.uncheck_all_layers_button.setToolTip("Uncheck all available point layers.\nES: Desmarca todas las capas de puntos disponibles.")
        self.uncheck_all_layers_button.clicked.connect(self.uncheck_all_calc_layers)
        layer_buttons.addWidget(self.refresh_calc_layers_button, 0, 0)
        layer_buttons.addWidget(self.check_current_layer_button, 0, 1)
        layer_buttons.addWidget(self.check_all_layers_button, 1, 0)
        layer_buttons.addWidget(self.uncheck_all_layers_button, 1, 1)
        layers_layout.addLayout(layer_buttons)
        layout.addWidget(layers_box)
        # The list is intentionally left empty on dialog opening/tab creation.
        # This avoids showing old project layers as if they were default input data.
        # Users can press "Refresh layer list", or the plugin will add layers here
        # after a new GBIF download/import/manual layer is created in the current session.

        opts = QGroupBox("Calculation parameters")
        form = QFormLayout(opts)
        _set_form_expanding_fields(form)
        self.analysis_crs = QComboBox()
        self.analysis_crs.setEditable(True)
        self.analysis_crs.setMaximumWidth(460)
        self.analysis_crs.setToolTip(
            "The dropdown only includes projected CRS values suitable for metric AOO/EOO calculations. "
            "You can type another valid EPSG code manually, for example EPSG:25830. "
            "GBIF and SRedList point inputs/outputs remain WGS84/EPSG:4326, but geographic CRS such as EPSG:4326 or EPSG:4258 are not included here because AOO grid cell size is in metres. Web Mercator/EPSG:3857 is also excluded because it is for display, not area calculation.\n"
            "ES: El desplegable solo incluye CRS proyectados adecuados para cálculos métricos de AOO/EOO. "
            "Puedes escribir manualmente otro código EPSG válido, por ejemplo EPSG:25830. "
            "Las entradas/salidas de puntos GBIF y SRedList se mantienen en WGS84/EPSG:4326, pero los CRS geográficos como EPSG:4326 o EPSG:4258 no se incluyen aquí porque el tamaño de celda AOO está en metros. Web Mercator/EPSG:3857 también se excluye porque sirve para visualización, no para cálculo de superficies."
        )
        for label, epsg in [
            ("ETRS89 / LAEA Europe - EPSG:3035 (recommended for AOO/EOO in Europe)", "EPSG:3035"),
            ("ETRS89 / UTM zone 29N - EPSG:25829", "EPSG:25829"),
            ("ETRS89 / UTM zone 30N - EPSG:25830", "EPSG:25830"),
            ("ETRS89 / UTM zone 31N - EPSG:25831", "EPSG:25831"),
            ("ED50 / UTM zone 29N - EPSG:23029", "EPSG:23029"),
            ("ED50 / UTM zone 30N - EPSG:23030", "EPSG:23030"),
            ("ED50 / UTM zone 31N - EPSG:23031", "EPSG:23031"),
            ("WGS84 / UTM zone 29N - EPSG:32629", "EPSG:32629"),
            ("WGS84 / UTM zone 30N - EPSG:32630", "EPSG:32630"),
            ("WGS84 / UTM zone 31N - EPSG:32631", "EPSG:32631"),
        ]:
            self.analysis_crs.addItem(label, epsg)
        self.analysis_crs.setCurrentIndex(0)
        self.cell_size = QDoubleSpinBox()
        self.cell_size.setRange(1, 100000)
        self.cell_size.setValue(2000)
        self.cell_size.setSuffix(" m")
        self.cell_size.setDecimals(0)
        self.cell_size.setMaximumWidth(160)
        self.cell_size.setToolTip(
            "IUCN standard AOO reference grid: 2 × 2 km = 2000 m. "
            "A different cell size requires explicit confirmation when calculating. / "
            "Cuadrícula AOO de referencia UICN: 2 × 2 km = 2000 m."
        )
        self.reset_cell_size_button = QPushButton("Reset to IUCN 2 km / Restablecer a 2 km")
        self.reset_cell_size_button.clicked.connect(lambda: self.cell_size.setValue(2000))
        cell_size_row = QWidget()
        cell_size_layout = QHBoxLayout(cell_size_row)
        cell_size_layout.setContentsMargins(0, 0, 0, 0)
        cell_size_layout.addWidget(self.cell_size)
        cell_size_layout.addWidget(self.reset_cell_size_button)
        cell_size_layout.addStretch()

        self.include_pending = QCheckBox("Also use points marked as ‘review before use’")
        self.include_pending.setChecked(False)
        self.deduplicate = QCheckBox("Remove exact spatial duplicates")
        self.deduplicate.setChecked(True)
        self.use_uncertainty_filter = QCheckBox("Filter by maximum uncertainty")
        self.use_uncertainty_filter.setChecked(True)
        self.max_uncertainty = QDoubleSpinBox()
        self.max_uncertainty.setRange(0, 1_000_000)
        self.max_uncertainty.setValue(1000)
        self.max_uncertainty.setSuffix(" m")
        self.max_uncertainty.setDecimals(0)
        self.max_uncertainty.setMaximumWidth(160)

        form.addRow("Analysis CRS for AOO/EOO / CRS de análisis para AOO/EOO", self.analysis_crs)
        form.addRow("AOO cell size (IUCN reference: 2000 m)", cell_size_row)
        form.addRow("Points under review", self.include_pending)
        form.addRow("Duplicates", self.deduplicate)
        form.addRow(self.use_uncertainty_filter, self.max_uncertainty)
        layout.addWidget(opts)

        iucn_box = QGroupBox("Required/conditional IUCN attributes for AOO and EOO")
        iucn_form = QFormLayout(iucn_box)
        _set_form_expanding_fields(iucn_form)
        this_year = datetime.now().year
        self.iucn_presence = QComboBox()
        self.iucn_presence.addItem("1 - Extant", 1)
        self.iucn_presence.addItem("3 - Possibly Extant", 3)
        self.iucn_presence.addItem("4 - Possibly Extinct", 4)
        self.iucn_presence.addItem("5 - Extinct", 5)
        self.iucn_presence.addItem("6 - Presence Uncertain", 6)
        self.iucn_presence.addItem("7 - Extant & Introduced", 7)
        self.iucn_presence.setMaximumWidth(360)

        self.iucn_origin = QComboBox()
        self.iucn_origin.addItem("1 - Native", 1)
        self.iucn_origin.addItem("2 - Reintroduced", 2)
        self.iucn_origin.addItem("3 - Introduced", 3)
        self.iucn_origin.addItem("4 - Vagrant", 4)
        self.iucn_origin.addItem("5 - Origin Uncertain", 5)
        self.iucn_origin.addItem("6 - Assisted Colonisation", 6)
        self.iucn_origin.addItem("7 - Mixed origin", 7)
        self.iucn_origin.setMaximumWidth(360)

        self.iucn_seasonal = QComboBox()
        self.iucn_seasonal.addItem("1 - Resident", 1)
        self.iucn_seasonal.addItem("2 - Breeding Season", 2)
        self.iucn_seasonal.addItem("3 - Non-breeding Season", 3)
        self.iucn_seasonal.addItem("4 - Passage", 4)
        self.iucn_seasonal.addItem("5 - Seasonal Occurrence Uncertain", 5)
        self.iucn_seasonal.setMaximumWidth(360)

        self.iucn_compiler = QLineEdit()
        self.iucn_compiler.setMaximumWidth(420)
        self.iucn_yrcompiled = QSpinBox()
        self.iucn_yrcompiled.setRange(1900, this_year + 1)
        self.iucn_yrcompiled.setValue(this_year)
        self.iucn_yrcompiled.setMaximumWidth(120)
        self.iucn_citation = QLineEdit()
        self.iucn_citation.setMaximumWidth(520)
        self.iucn_subspecies = QLineEdit()
        self.iucn_subspecies.setMaximumWidth(320)
        self.iucn_data_sens = QComboBox()
        self.iucn_data_sens.addItem("0 - Not sensitive", 0)
        self.iucn_data_sens.addItem("1 - Sensitive", 1)
        self.iucn_data_sens.setMaximumWidth(200)
        self.iucn_sens_comm = QLineEdit()
        self.iucn_sens_comm.setMaximumWidth(520)

        iucn_form.addRow("sci_name *", QLabel("will be taken from the scientific name in the GBIF tab"))
        iucn_form.addRow("presence *", self.iucn_presence)
        iucn_form.addRow("origin *", self.iucn_origin)
        iucn_form.addRow("seasonal * if applicable", self.iucn_seasonal)
        iucn_form.addRow("compiler *", self.iucn_compiler)
        iucn_form.addRow("yrcompiled *", self.iucn_yrcompiled)
        iucn_form.addRow("citation *", self.iucn_citation)
        iucn_form.addRow("subspecies if applicable", self.iucn_subspecies)
        iucn_form.addRow("data_sens if sensitive", self.iucn_data_sens)
        iucn_form.addRow("sens_comm * if data_sens=1", self.iucn_sens_comm)
        note = QLabel(
            "EN: Required/conditional IUCN fields for the AOO and EOO layers. "
            "compiler and citation are blank by default. generalisd is added automatically: AOO=0 and EOO=1.\n\n"
            "ES: Campos IUCN obligatorios/condicionales para las capas AOO y EOO. "
            "compiler y citation quedan vacíos por defecto. generalisd se añade automáticamente: AOO=0 y EOO=1."
        )
        note.setWordWrap(True)
        iucn_form.addRow("Note", note)
        self.iucn_fields_help_button = QPushButton("Create IUCN AOO/EOO attribute guide")
        self.iucn_fields_help_button.setToolTip("Create a guide table for the required IUCN attributes of the AOO and EOO layers.\nES: Crea una tabla guía para los atributos IUCN obligatorios de las capas AOO y EOO.")
        self.iucn_fields_help_button.clicked.connect(self.create_iucn_polygon_field_guide)
        iucn_form.addRow("Help", self.iucn_fields_help_button)
        layout.addWidget(iucn_box)

        threshold_note = QLabel(
            "EN: The report adds an indicative category according to the spatial AOO and EOO thresholds of IUCN Criterion B. "
            "It does not replace a formal Red List assessment, because the plugin does not evaluate the additional subcriteria.\n\n"
            "ES: El informe añade una categoría orientativa según los umbrales espaciales de AOO y EOO del Criterio B de IUCN. "
            "No sustituye una evaluación formal de Lista Roja, porque el plugin no evalúa los subcriterios adicionales."
        )
        threshold_note.setWordWrap(True)
        layout.addWidget(threshold_note)

        buttons = QHBoxLayout()
        self.calc_button = QPushButton("Calculate AOO/EOO")
        self.calc_button.setToolTip("Run the AOO/EOO calculation using only the checked point layers.\nES: Ejecuta el cálculo AOO/EOO usando solo las capas de puntos marcadas.")
        self.calc_button.clicked.connect(self.calculate)
        buttons.addStretch(1)
        buttons.addWidget(self.calc_button)
        layout.addLayout(buttons)
        layout.addStretch(1)
        scroll.setWidget(content)
        outer.addWidget(scroll)
        return tab

    def _make_report_tab(self) -> QWidget:
        tab = QWidget()
        layout = QVBoxLayout(tab)
        info = QLabel(
            "EN: This tab prepares Point Distribution from the points used in the last calculation in tab 3. "
            "If you selected several layers in tab 3, the selected records from all of them will be included here.\n\n"
            "ES: Esta pestaña prepara Point Distribution a partir de los puntos usados en el último cálculo de la pestaña 3. "
            "Si en la pestaña 3 marcaste varias capas, aquí se incluirán los registros seleccionados de todas ellas."
        )
        info.setWordWrap(True)
        layout.addWidget(info)

        csv_box = QGroupBox("Point Distribution")
        csv_layout = QVBoxLayout(csv_box)
        csv_hint = QLabel(
            "EN: The Point Distribution table and CSV will have exactly 21 fields, in this order: "
            "sci_name, presence, origin, seasonal, compiler, yrcompiled, citation, dec_lat, dec_long, spatialref, "
            "subspecies, subpop, data_sens, sens_comm, event_year, source, basisofrec, catalog_no, dist_comm, island, tax_comm. "
            "The shapefile is exported as a point layer in WGS84/EPSG:4326 with those same attributes. This is the output intended for loading a layer compatible with the SRedList platform.\n\n"
            "ES: La tabla y el CSV Point Distribution tendrán exactamente 21 campos, en este orden: "
            "sci_name, presence, origin, seasonal, compiler, yrcompiled, citation, dec_lat, dec_long, spatialref, "
            "subspecies, subpop, data_sens, sens_comm, event_year, source, basisofrec, catalog_no, dist_comm, island, tax_comm. "
            "El shapefile se exporta como capa de puntos en WGS84/EPSG:4326 con esos mismos atributos. Esta es la salida pensada para cargar una capa compatible con la plataforma SRedList."
        )
        csv_hint.setWordWrap(True)
        csv_layout.addWidget(csv_hint)
        buttons = QGridLayout()
        self.create_point_distribution_button = QPushButton("Create Point Distribution table in QGIS")
        self.create_point_distribution_button.setToolTip("Create a Point Distribution attribute table in QGIS from the last calculation.\nES: Crea una tabla Point Distribution en QGIS a partir del último cálculo.")
        self.create_point_distribution_button.clicked.connect(self.create_point_distribution_table)
        self.create_point_distribution_shp_layer_button = QPushButton("Create Point Distribution layer compatible with the SRedList platform")
        self.create_point_distribution_shp_layer_button.setToolTip("Create a Point Distribution point layer compatible with the SRedList platform.\nES: Crea una capa de puntos Point Distribution compatible con la plataforma SRedList.")
        self.create_point_distribution_shp_layer_button.setToolTip("Create in QGIS a Point Distribution point layer compatible with the SRedList platform, using the points selected in the last calculation.\nES: Crea en QGIS una capa de puntos Point Distribution compatible con la plataforma SRedList, usando los puntos seleccionados del último cálculo.")
        self.create_point_distribution_shp_layer_button.clicked.connect(self.create_point_distribution_shapefile_layer)
        self.save_point_distribution_button = QPushButton("Save Point Distribution CSV...")
        self.save_point_distribution_button.setToolTip("Save the Point Distribution output as CSV.\nES: Guarda la salida Point Distribution como CSV.")
        self.save_point_distribution_button.clicked.connect(self.save_point_distribution_csv)
        self.save_point_distribution_shp_button = QPushButton("Save Point Distribution shapefile...")
        self.save_point_distribution_shp_button.setToolTip("Save the Point Distribution output as a shapefile.\nES: Guarda la salida Point Distribution como shapefile.")
        self.save_point_distribution_shp_button.clicked.connect(self.save_point_distribution_shapefile)
        self.point_distribution_help_button = QPushButton("Point Distribution field guide")
        self.point_distribution_help_button.setToolTip("Open a guide to the fields used in the Point Distribution output.\nES: Abre una guía de los campos utilizados en la salida Point Distribution.")
        self.point_distribution_help_button.clicked.connect(self.show_point_distribution_help)
        buttons.addWidget(self.create_point_distribution_button, 0, 0)
        buttons.addWidget(self.create_point_distribution_shp_layer_button, 0, 1)
        buttons.addWidget(self.save_point_distribution_button, 1, 0)
        buttons.addWidget(self.save_point_distribution_shp_button, 1, 1)
        buttons.addWidget(self.point_distribution_help_button, 2, 0, 1, 2)
        csv_layout.addLayout(buttons)
        layout.addWidget(csv_box)
        layout.addStretch(1)
        return tab


    def _make_gbif_citation_tab(self) -> QWidget:
        tab = QWidget()
        outer = QVBoxLayout(tab)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        content = QWidget()
        layout = QVBoxLayout(content)

        info = QLabel(
            "EN: This tab creates the correct GBIF citation for the GBIF records that actually entered the calculation. "
            "The workflow uses only the official GBIF occurrence download route: used gbifIDs → official GBIF download → DOI → citation. "
            "It does not use Derived Dataset, datasetKey/count or an external public URL.\n\n"
            "ES: Esta pestaña crea la cita GBIF correcta para los registros GBIF que han entrado realmente en el cálculo. "
            "El flujo usa solo la vía oficial de descarga de ocurrencias de GBIF: gbifID usados → descarga oficial GBIF → DOI → cita. "
            "No usa Derived Dataset, datasetKey/count ni URL pública externa."
        )
        info.setWordWrap(True)
        layout.addWidget(info)

        step1 = QGroupBox("Step 1. Prepare the used gbifIDs")
        step1_layout = QVBoxLayout(step1)
        step1_text = QLabel(
            "EN: After calculating AOO/EOO, press the button to extract the gbifIDs from the points used. "
            "This is step 1 because GBIF needs the exact list of records used in the calculation. "
            "The list includes only GBIF records; user-added points do not have a GBIF DOI and must be cited separately.\n\n"
            "ES: Después de calcular AOO/EOO, pulsa el botón para extraer los gbifID de los puntos usados. "
            "Este es el paso 1 porque GBIF necesita la lista exacta de registros usados en el cálculo. "
            "La lista incluye solo registros de GBIF; los puntos propios no tienen DOI GBIF y deben citarse aparte."
        )
        step1_text.setWordWrap(True)
        step1_layout.addWidget(step1_text)
        row1 = QHBoxLayout()
        self.prepare_gbif_ids_button = QPushButton("1. Prepare list of used gbifIDs")
        self.prepare_gbif_ids_button.setToolTip("Extract the gbifIDs actually used in the last calculation.\nES: Extrae los gbifID realmente usados en el último cálculo.")
        self.prepare_gbif_ids_button.clicked.connect(self.prepare_gbif_download_ids)
        self.copy_gbif_ids_button = QPushButton("Copy gbifID")
        self.copy_gbif_ids_button.setToolTip("Copy the used gbifIDs to the clipboard for review.\nES: Copia los gbifID usados al portapapeles para revisión.")
        self.copy_gbif_ids_button.clicked.connect(self.copy_gbif_ids)
        row1.addWidget(self.prepare_gbif_ids_button)
        row1.addWidget(self.copy_gbif_ids_button)
        row1.addStretch(1)
        step1_layout.addLayout(row1)
        layout.addWidget(step1)

        step2 = QGroupBox("Step 2. Request an official GBIF download")
        step2_layout = QVBoxLayout(step2)
        step2_text = QLabel(
            "EN: With this option you do not need to paste the list into any website: the plugin sends it directly to the official GBIF download API. "
            "GBIF first returns a download key. The DOI appears when the download is finished. You need your GBIF.org username and password; the password is not stored.\n\n"
            "ES: Con esta opción no tienes que pegar la lista en ninguna web: el plugin la envía directamente a la API oficial de descargas de GBIF. "
            "GBIF responde primero con una clave de descarga. El DOI aparece cuando la descarga termina. Necesitas usuario y contraseña de GBIF.org; la contraseña no se guarda."
        )
        step2_text.setWordWrap(True)
        step2_layout.addWidget(step2_text)
        form_box = QWidget()
        form = QFormLayout(form_box)
        _set_form_expanding_fields(form)
        self.gbif_download_user = QLineEdit()
        self.gbif_download_user.setPlaceholderText("GBIF username, not email")
        self.gbif_download_password = QLineEdit()
        self.gbif_download_password.setEchoMode(_line_edit_password())
        self.gbif_download_email = QLineEdit()
        self.gbif_download_email.setPlaceholderText("GBIF notification email")
        self.gbif_download_format = QComboBox()
        self.gbif_download_format.addItem("SIMPLE_CSV", "SIMPLE_CSV")
        self.gbif_download_format.addItem("DWCA", "DWCA")
        form.addRow("GBIF username* (not email)", self.gbif_download_user)
        form.addRow("GBIF password*", self.gbif_download_password)
        form.addRow("Notification email", self.gbif_download_email)
        form.addRow("Format", self.gbif_download_format)
        step2_layout.addWidget(form_box)
        row2 = QHBoxLayout()
        self.request_gbif_download_button = QPushButton("2. Request official download and DOI")
        self.request_gbif_download_button.setToolTip("Send the used gbifIDs to the official GBIF download API in order to obtain a DOI.\nES: Envía los gbifID usados a la API oficial de descargas de GBIF para obtener un DOI.")
        self.request_gbif_download_button.clicked.connect(self.request_gbif_occurrence_download)
        self.open_gbif_download_button = QPushButton("Open my GBIF downloads")
        self.open_gbif_download_button.setToolTip("Open the GBIF page with your downloads in the browser.\nES: Abre en el navegador la página de GBIF con tus descargas.")
        self.open_gbif_download_button.clicked.connect(lambda: QDesktopServices.openUrl(QUrl("https://www.gbif.org/occurrence/download")))
        row2.addWidget(self.request_gbif_download_button)
        row2.addWidget(self.open_gbif_download_button)
        row2.addStretch(1)
        step2_layout.addLayout(row2)
        layout.addWidget(step2)

        step3 = QGroupBox("Step 3. Check whether the DOI is ready")
        step3_layout = QVBoxLayout(step3)
        step3_text = QLabel(
            "EN: The GBIF download is asynchronous. It may take from a few seconds to several minutes. "
            "When the status is SUCCEEDED, GBIF will return a citable DOI.\n\n"
            "ES: La descarga de GBIF es asíncrona. Puede tardar desde unos segundos hasta varios minutos. "
            "Cuando el estado sea SUCCEEDED, GBIF devolverá un DOI citable."
        )
        step3_text.setWordWrap(True)
        step3_layout.addWidget(step3_text)
        key_row = QHBoxLayout()
        self.gbif_download_key_edit = QLineEdit()
        self.gbif_download_key_edit.setPlaceholderText("GBIF download key")
        self.check_gbif_download_button = QPushButton("3. Check status / DOI")
        self.check_gbif_download_button.setToolTip("Check the status of the GBIF download and retrieve the DOI when ready.\nES: Comprueba el estado de la descarga de GBIF y recupera el DOI cuando esté listo.")
        self.check_gbif_download_button.clicked.connect(self.check_gbif_occurrence_download)
        key_row.addWidget(QLabel("Key:"))
        key_row.addWidget(self.gbif_download_key_edit, 1)
        key_row.addWidget(self.check_gbif_download_button)
        step3_layout.addLayout(key_row)
        layout.addWidget(step3)

        step4 = QGroupBox("Step 4. Result and citation")
        step4_layout = QVBoxLayout(step4)
        self.gbif_download_result = QTextEdit()
        self.gbif_download_result.setReadOnly(True)
        self.gbif_download_result.setMinimumHeight(220)
        self.gbif_download_result.setPlainText(
            "EN:\n"
            "1) Calculate AOO/EOO in tab 3.\n"
            "2) Press ‘Prepare list of used gbifIDs’.\n"
            "3) Enter your GBIF username/password and request the official download.\n"
            "4) Copy the download key or press ‘Check status / DOI’ until GBIF returns SUCCEEDED.\n"
            "5) Cite the GBIF DOI that will appear here.\n\n"
            "Note: the GBIF DOI covers only records coming from GBIF. User-added points must be cited with their own independent source.\n\n"
            "ES:\n"
            "1) Calcula AOO/EOO en la pestaña 3.\n"
            "2) Pulsa ‘Prepare list of used gbifIDs’.\n"
            "3) Introduce tu usuario/contraseña de GBIF y solicita la descarga oficial.\n"
            "4) Copia la clave de descarga o pulsa ‘Check status / DOI’ hasta que GBIF devuelva SUCCEEDED.\n"
            "5) Cita el DOI de GBIF que aparecerá aquí.\n\n"
            "Nota: el DOI GBIF cubre únicamente los registros procedentes de GBIF. Los puntos propios deben citarse con su fuente independiente."
        )
        step4_layout.addWidget(self.gbif_download_result)
        row4 = QHBoxLayout()
        self.copy_gbif_citation_button = QPushButton("Copy citation")
        self.copy_gbif_citation_button.setToolTip("Copy the recommended GBIF citation to the clipboard.\nES: Copia la cita recomendada de GBIF al portapapeles.")
        self.copy_gbif_citation_button.clicked.connect(self.copy_gbif_citation)
        self.open_gbif_citation_button = QPushButton("Open GBIF citation guide")
        self.open_gbif_citation_button.setToolTip("Open the official GBIF guidance on citing downloads.\nES: Abre la guía oficial de GBIF sobre cómo citar descargas.")
        self.open_gbif_citation_button.clicked.connect(lambda: QDesktopServices.openUrl(QUrl("https://www.gbif.org/citation-guidelines")))
        row4.addWidget(self.copy_gbif_citation_button)
        row4.addWidget(self.open_gbif_citation_button)
        row4.addStretch(1)
        step4_layout.addLayout(row4)
        layout.addWidget(step4)
        layout.addStretch(1)
        scroll.setWidget(content)
        outer.addWidget(scroll)
        return tab

    def _make_check_list(self, options) -> QListWidget:
        widget = QListWidget()
        for value, checked, tooltip in options:
            item = QListWidgetItem(value)
            item.setFlags(item.flags() | _qt_item_user_checkable())
            item.setCheckState(_qt_checked() if checked else _qt_unchecked())
            item.setToolTip(tooltip)
            widget.addItem(item)
        return widget

    def show_point_distribution_help(self):
        dialog = PointDistributionHelpDialog(self)
        _dialog_exec(dialog)


    def reset_gbif_tab(self):
        """Reset the GBIF search/filter tab to its default values."""
        self.scientific_name.clear()
        self.taxon_key.clear()
        self.country_code.clear()
        self.year_min.setValue(0)
        self.year_max.setValue(0)
        self.occurrence_status.setCurrentText("PRESENT")
        self.exclude_geospatial_issues.setChecked(True)
        self.coordinatecleaner_filter.setChecked(True)
        if hasattr(self, "gbif_uncertainty_filter"):
            self.gbif_uncertainty_filter.setChecked(False)
        if hasattr(self, "gbif_uncertainty_combo"):
            self.gbif_uncertainty_combo.setCurrentText("1 km")
        self.last_filter_removed = []
        self.assess_infraspecific.setChecked(False)
        self.infraspecific_epithet.clear()
        for widget in [self.synonym_1, self.synonym_2, self.synonym_3, self.synonym_4]:
            widget.clear()
        for list_widget, options in [(self.basis_list, BASIS_OPTIONS), (self.establishment_list, ESTABLISHMENT_OPTIONS)]:
            for i, (_value, checked, _tooltip) in enumerate(options):
                item = list_widget.item(i)
                if item is not None:
                    item.setCheckState(_qt_checked() if checked else _qt_unchecked())
        self.filter_establishment.setChecked(False)
        self._log("Filtros GBIF reseteados a valores por defecto.")


    # ------------------------------------------------------------- utilities
    def _log(self, text: str):
        stamp = datetime.now().strftime("%H:%M:%S")
        self.log.append(f"[{stamp}] {text}")

    def _checked_values(self, widget: QListWidget) -> list[str]:
        values = []
        for i in range(widget.count()):
            item = widget.item(i)
            if item.checkState() == _qt_checked():
                values.append(item.text())
        return values

    def _synonym_names(self) -> list[str]:
        names = []
        for widget in [self.synonym_1, self.synonym_2, self.synonym_3, self.synonym_4]:
            value = widget.text().strip()
            if value and value not in names:
                names.append(value)
        return names

    def _gbif_uncertainty_threshold_m(self):
        if not hasattr(self, "gbif_uncertainty_combo"):
            return None
        text = (self.gbif_uncertainty_combo.currentText() or "").strip().lower()
        if not text or "sin" in text:
            return None
        match = re.search(r"[-+]?\d+(?:[\.,]\d+)?", text)
        if match:
            try:
                value = float(match.group(0).replace(",", "."))
                if "km" in text:
                    value *= 1000.0
                return value
            except ValueError:
                return None
        data = self.gbif_uncertainty_combo.currentData()
        if data in (None, ""):
            return None
        try:
            return float(data)
        except (TypeError, ValueError):
            return None

    def _gbif_year_bounds(self):
        ymin = self.year_min.value() if hasattr(self, "year_min") and self.year_min.value() else None
        ymax = self.year_max.value() if hasattr(self, "year_max") and self.year_max.value() else None
        return ymin, ymax

    def _apply_local_year_filter(self, records):
        ymin, ymax = self._gbif_year_bounds()
        if ymin is None and ymax is None:
            return records, []
        kept = []
        removed = []
        for rec in records:
            raw_year = rec.get("year")
            try:
                year_value = int(raw_year) if raw_year not in (None, "") else None
            except (TypeError, ValueError):
                year_value = None
            if year_value is None:
                kept.append(rec)
                continue
            if ymin is not None and year_value < ymin:
                removed.append((rec, f"Year filter: {year_value} < minimum year {ymin}"))
            elif ymax is not None and year_value > ymax:
                removed.append((rec, f"Year filter: {year_value} > maximum year {ymax}"))
            else:
                kept.append(rec)
        return kept, removed

    def _build_gbif_params(self) -> dict:
        params = {"hasCoordinate": "true"}
        taxon_key = self.taxon_key.text().strip()
        if taxon_key:
            params["taxonKey"] = taxon_key
        else:
            name = self.scientific_name.text().strip()
            if not name:
                raise ValueError("Enter a scientific name or a taxonKey.")
            # GBIF can search by scientificName, but taxonKey is more reproducible.
            params["scientificName"] = name

        if self.country_code.text().strip():
            params["country"] = self.country_code.text().strip().upper()

        # El filtro de año se aplica localmente después de descargar los registros,
        # para que los registros descartados puedan auditarse en la tabla
        # “GBIF registros eliminados por filtros”.
        if self.occurrence_status.currentText() != "no filtrar":
            params["occurrenceStatus"] = self.occurrence_status.currentText()

        basis = self._checked_values(self.basis_list)
        if basis:
            params["basisOfRecord"] = basis

        if self.filter_establishment.isChecked():
            est = self._checked_values(self.establishment_list)
            if est:
                params["establishmentMeans"] = est

        if self.exclude_geospatial_issues.isChecked():
            params["hasGeospatialIssue"] = "false"
        return params


    def _motivo_coordinatecleaner_es(self, reason: str) -> str:
        return COORDINATECLEANER_REASON_TRANSLATION.get(str(reason or ""), str(reason or ""))

    def create_coordinatecleaner_criteria_table(self):
        """Crea una tabla en QGIS con los criterios del filtro CoordinateCleaner aplicado."""
        layer = QgsVectorLayer("None", "Criterios del filtro CoordinateCleaner", "memory")
        provider = layer.dataProvider()
        provider.addAttributes([
            QgsField("motivo", QVariant.String),
            QgsField("que_elimina", QVariant.String),
        ])
        layer.updateFields()
        features = []
        for motivo, descripcion in COORDINATECLEANER_CRITERIOS_ES:
            feat = QgsFeature(layer.fields())
            feat.setAttributes([motivo, descripcion])
            features.append(feat)
        provider.addFeatures(features)
        layer.updateFields()
        layer.updateExtents()
        QgsProject.instance().addMapLayer(layer)
        self._log("Tabla creada con los criterios del filtro tipo CoordinateCleaner.")
        self.iface.messageBar().pushSuccess("IUCN Red List calculator", "Tabla de criterios del filtro creada en el proyecto.")

    def create_filtered_records_table(self):
        """Crea una tabla en QGIS con los registros retirados por filtros automáticos."""
        removed = getattr(self, "last_filter_removed", []) or []
        if not removed:
            QMessageBox.information(
                self,
                "Registros eliminados",
                "There are no records removed by the year, CoordinateCleaner or uncertainty filters in the last GBIF download."
            )
            return

        layer = QgsVectorLayer("None", "GBIF registros eliminados por filtros", "memory")
        provider = layer.dataProvider()
        fields = [
            ("motivo", QVariant.String),
            ("gbifID", QVariant.String),
            ("nombre_cientifico", QVariant.String),
            ("latitud", QVariant.Double),
            ("longitud", QVariant.Double),
            ("incertidumbre_m", QVariant.Double),
            ("base_registro", QVariant.String),
            ("estado_ocurrencia", QVariant.String),
            ("origen_establecimiento", QVariant.String),
            ("fecha_evento", QVariant.String),
            ("anio", QVariant.Int),
            ("pais", QVariant.String),
            ("datasetKey", QVariant.String),
            ("institucion", QVariant.String),
            ("coleccion", QVariant.String),
            ("incidencias_gbif", QVariant.String),
        ]
        provider.addAttributes([QgsField(name, typ) for name, typ in fields])
        layer.updateFields()

        def safe_float(value):
            try:
                if value in (None, ""):
                    return None
                return float(value)
            except (TypeError, ValueError):
                return None

        def safe_int(value):
            try:
                if value in (None, ""):
                    return None
                return int(value)
            except (TypeError, ValueError):
                return None

        features = []
        for rec, reason in removed:
            reason_text = str(reason or "")
            if reason_text.startswith("CoordinateCleaner: "):
                raw_reason = reason_text.split(": ", 1)[1]
                reason_text = "CoordinateCleaner: " + self._motivo_coordinatecleaner_es(raw_reason)
            feat = QgsFeature(layer.fields())
            feat.setAttributes([
                reason_text,
                str(rec.get("gbifID", "") or ""),
                str(rec.get("scientificName", "") or ""),
                safe_float(rec.get("decimalLatitude")),
                safe_float(rec.get("decimalLongitude")),
                safe_float(rec.get("coordinateUncertaintyInMeters")),
                str(rec.get("basisOfRecord", "") or ""),
                str(rec.get("occurrenceStatus", "") or ""),
                str(rec.get("establishmentMeans", "") or ""),
                str(rec.get("eventDate", "") or ""),
                safe_int(rec.get("year")),
                str(rec.get("countryCode", "") or ""),
                str(rec.get("datasetKey", "") or ""),
                str(rec.get("institutionCode", "") or ""),
                str(rec.get("collectionCode", "") or ""),
                str(rec.get("issues", "") or ""),
            ])
            features.append(feat)
        provider.addFeatures(features)
        layer.updateFields()
        layer.updateExtents()
        QgsProject.instance().addMapLayer(layer)
        self._log(f"Table created with {len(features)} records removed by automatic filters.")
        self.iface.messageBar().pushSuccess("IUCN Red List calculator", "Tabla de registros eliminados creada en el proyecto.")

    # -------------------------------------------------------------- GBIF ops
    def resolve_taxon(self):
        try:
            result = match_species(self.scientific_name.text().strip())
        except GbifError as exc:
            QMessageBox.warning(self, "GBIF", str(exc))
            return

        usage_key = result.get("usageKey") or result.get("acceptedUsageKey")
        if usage_key:
            self.taxon_key.setText(str(usage_key))
        msg = (
            f"Match GBIF: {result.get('scientificName', '')} | "
            f"rank={result.get('rank', '')} | confidence={result.get('confidence', '')} | "
            f"status={result.get('status', '')} | usageKey={usage_key}"
        )
        self._log(msg)

    def preview_facets(self):
        try:
            params = self._build_gbif_params()
            data = occurrence_facets(params)
        except (GbifError, ValueError) as exc:
            QMessageBox.warning(self, "GBIF", str(exc))
            return

        self._log(f"GBIF total aproximado con filtros principales: {data.get('count', 0)}")
        if self._synonym_names():
            self._log("Note: optional synonyms are included during the download; this preview shows the main query.")
        facets = data.get("facets") or []
        for facet in facets:
            field = facet.get("field", "")
            counts = facet.get("counts") or []
            summary = ", ".join(f"{c.get('name')}={c.get('count')}" for c in counts[:12])
            self._log(f"  {field}: {summary}")

    def download_gbif(self):
        try:
            params = self._build_gbif_params()
            self._log(f"Downloading GBIF with main parameters: {params}")

            def progress(done, total):
                total_txt = total if total is not None else "?"
                self._log(f"  descargados {done} de {total_txt}")
                QApplication.processEvents()

            raw_records = search_occurrences(params, progress_callback=progress)

            # Optional synonyms: GBIF occurrence/search has no single OR widget here,
            # so we query each synonym separately and deduplicate by gbifID.
            synonyms = self._synonym_names()
            if synonyms:
                self._log(f"Also searching synonyms: {', '.join(synonyms)}")
                for syn in synonyms:
                    syn_params = dict(params)
                    syn_params.pop("taxonKey", None)
                    syn_params["scientificName"] = syn
                    self._log(f"  Downloading synonym: {syn}")
                    raw_records.extend(search_occurrences(syn_params, progress_callback=progress))

            # Deduplicate GBIF records before creating the QGIS layer.
            seen_gbif_ids = set()
            slim_records = []
            for record in raw_records:
                rec = slim_record(record)
                gbif_id = rec.get("gbifID", "")
                if gbif_id and gbif_id in seen_gbif_ids:
                    continue
                if gbif_id:
                    seen_gbif_ids.add(gbif_id)
                slim_records.append(rec)

            self.last_filter_removed = []
            records = slim_records

            records, removed_year = self._apply_local_year_filter(records)
            if removed_year:
                self.last_filter_removed.extend(removed_year)
                self._log(f"Year filter applied: {len(removed_year)} records removed before creating the GBIF layer.")
            elif self.year_min.value() or self.year_max.value():
                self._log("Year filter applied: no records removed.")

            if self.coordinatecleaner_filter.isChecked():
                records, flagged = coordinatecleaner_filter_records(records)
                for rec, reason in flagged:
                    self.last_filter_removed.append((rec, f"CoordinateCleaner: {self._motivo_coordinatecleaner_es(reason)}"))
                self._log(f"Filtro tipo CoordinateCleaner aplicado: {len(flagged)} registros retirados antes de crear la capa GBIF.")
                if flagged:
                    reasons = {}
                    for _rec, reason in flagged:
                        reason_es = self._motivo_coordinatecleaner_es(reason)
                        reasons[reason_es] = reasons.get(reason_es, 0) + 1
                    self._log("  Motivos: " + "; ".join(f"{k}={v}" for k, v in sorted(reasons.items())))

            if self.gbif_uncertainty_filter.isChecked():
                threshold = self._gbif_uncertainty_threshold_m()
                if threshold is not None:
                    kept = []
                    removed_uncertainty = []
                    for rec in records:
                        try:
                            uncertainty = rec.get("coordinateUncertaintyInMeters")
                            uncertainty_value = None if uncertainty in (None, "") else float(uncertainty)
                        except (TypeError, ValueError):
                            uncertainty_value = None
                        if uncertainty_value is not None and uncertainty_value > threshold:
                            reason = f"Incertidumbre: {uncertainty_value:g} m > {threshold:g} m"
                            removed_uncertainty.append((rec, reason))
                            self.last_filter_removed.append((rec, reason))
                        else:
                            kept.append(rec)
                    records = kept
                    self._log(f"Filtro de incertidumbre aplicado: {len(removed_uncertainty)} registros retirados con incertidumbre > {threshold:g} m.")
                    # Los registros sin coordinateUncertaintyInMeters se mantienen para no eliminar datos potencialmente válidos sin revisión.

            layer_name = "GBIF occurrences AOO_EOO"
            if self.scientific_name.text().strip():
                layer_name = f"GBIF {self.scientific_name.text().strip()}"
            self.gbif_layer = create_occurrence_layer(records, layer_name)
            self.gbif_layer.setCustomProperty("aoo_eoo_gbif_pro_layer_type", "gbif_points")
            QgsProject.instance().addMapLayer(self.gbif_layer)
            self.gbif_layer_id = self.gbif_layer.id()
            if self.layer_combo is not None:
                self.layer_combo.setLayer(self.gbif_layer)
            self._check_only_calc_layer(self.gbif_layer)
            self._log(f"GBIF layer created: {self.gbif_layer.featureCount()} valid points with coordinates.")
            self.iface.messageBar().pushSuccess("IUCN Red List calculator", "GBIF download finished and added to the project.")
        except (GbifError, ValueError, Exception) as exc:  # pylint: disable=broad-except
            QMessageBox.critical(self, "Error al descargar GBIF", str(exc))
            self._log(f"ERROR GBIF: {exc}")

    # -------------------------------------------------------------- GBIF layer
    def _get_existing_gbif_layer(self):
        """Return the current GBIF occurrence layer, or None if it was removed."""
        if _layer_is_usable(self.gbif_layer):
            return self.gbif_layer

        self.gbif_layer = None
        project = QgsProject.instance()

        if self.gbif_layer_id:
            layer = project.mapLayer(self.gbif_layer_id)
            if _layer_is_usable(layer):
                self.gbif_layer = layer
                return layer
            self.gbif_layer_id = None

        for layer in project.mapLayers().values():
            try:
                if layer.customProperty("aoo_eoo_gbif_pro_layer_type") == "gbif_points" and _layer_is_usable(layer):
                    self.gbif_layer = layer
                    self.gbif_layer_id = layer.id()
                    return layer
            except RuntimeError:
                continue
        return None


    # ------------------------------------------------------------- layer selection
    def _is_probably_point_layer(self, layer) -> bool:
        if not _layer_is_usable(layer):
            return False
        try:
            wkb_text = str(layer.wkbType()).lower()
            geom_text = str(layer.geometryType()).lower()
            if "point" in wkb_text or "point" in geom_text:
                return True
        except (AttributeError, RuntimeError, TypeError) as exc:
            # Some QGIS bindings cannot stringify their geometry enums. Try
            # the capability-based check below instead of hiding the failure.
            self._log(f"Layer geometry metadata unavailable; using compatibility check: {exc}")
        try:
            # Be permissive for QGIS 4 and CSV layers: run_aoo_eoo validates
            # feature geometries again and ignores non-point geometries safely.
            return hasattr(layer, "getFeatures") and hasattr(layer, "featureCount") and hasattr(layer, "crs")
        except Exception:
            return False

    def _update_calc_selection_summary(self, _changed_item=None):
        """Display the exact input selection, independently of QGIS layer visibility."""
        if self.calc_layers_list is None:
            return
        selected = [self.calc_layers_list.item(i).text()
                    for i in range(self.calc_layers_list.count())
                    if self.calc_layers_list.item(i).checkState() == _qt_checked()]
        label = "; ".join(selected) if selected else "none / ninguna"
        self.calc_selection_summary.setText(
            f"Selected for calculation / Capas seleccionadas ({len(selected)}): {label}"
        )

    def refresh_calc_layers(self, apply_defaults=None):
        """Refresh the list without implicitly enabling stale/manual/GBIF layers.

        Explicit check states are preserved for existing project layer IDs.
        New layers are selected exclusively at the point where they are created.
        The apply_defaults parameter is retained for backward compatibility.
        """
        if self.calc_layers_list is None:
            return
        checked_ids = {
            self.calc_layers_list.item(i).data(_qt_user_role())
            for i in range(self.calc_layers_list.count())
            if self.calc_layers_list.item(i).checkState() == _qt_checked()
        }
        self.calc_layers_list.blockSignals(True)
        try:
            self.calc_layers_list.clear()
            for layer in QgsProject.instance().mapLayers().values():
                if not self._is_probably_point_layer(layer):
                    continue
                try:
                    item = QListWidgetItem(f"{layer.name()} ({layer.featureCount()} records)")
                    item.setFlags(_qt_item_is_enabled() | _qt_item_is_selectable() | _qt_item_user_checkable())
                    item.setData(_qt_user_role(), layer.id())
                    item.setToolTip(f"{layer.name()} | {layer.source() if hasattr(layer, 'source') else ''}")
                    item.setCheckState(_qt_checked() if layer.id() in checked_ids else _qt_unchecked())
                    self.calc_layers_list.addItem(item)
                except RuntimeError as exc:
                    self._log(f"A deleted or unavailable layer was skipped during refresh: {exc}")
        finally:
            self.calc_layers_list.blockSignals(False)
        self._update_calc_selection_summary()

    def check_current_calc_layer(self):
        if self.calc_layers_list is None:
            return
        self.refresh_calc_layers(apply_defaults=False)
        try:
            fallback = self.layer_combo.currentLayer() if self.layer_combo is not None else None
            current = self.iface.activeLayer() or fallback
            current_id = current.id() if _layer_is_usable(current) else ""
        except Exception:
            current_id = ""
        if not current_id:
            return
        for i in range(self.calc_layers_list.count()):
            item = self.calc_layers_list.item(i)
            if item.data(_qt_user_role()) == current_id:
                item.setCheckState(_qt_checked())

    def check_all_calc_layers(self):
        if self.calc_layers_list is None:
            return
        self.refresh_calc_layers(apply_defaults=False)
        for i in range(self.calc_layers_list.count()):
            self.calc_layers_list.item(i).setCheckState(_qt_checked())

    def uncheck_all_calc_layers(self):
        if self.calc_layers_list is None:
            return
        for i in range(self.calc_layers_list.count()):
            self.calc_layers_list.item(i).setCheckState(_qt_unchecked())

    def _on_tab_changed(self, index):
        # Do not auto-refresh tab 3 when it is opened. The layer list should not
        # show old project/test layers by default; it is refreshed explicitly with
        # the button or automatically only after this plugin creates/imports data.
        return

    def _selected_calc_layers(self):
        layers = []
        project = QgsProject.instance()
        if self.calc_layers_list is not None:
            for i in range(self.calc_layers_list.count()):
                item = self.calc_layers_list.item(i)
                if item.checkState() != _qt_checked():
                    continue
                layer = project.mapLayer(item.data(_qt_user_role()))
                if _layer_is_usable(layer) and layer not in layers:
                    layers.append(layer)
        return layers

    def _iucn_criterion_b_inputs(self):
        # Se conserva por compatibilidad interna, pero la versión actual solo
        # informa la categoría orientativa según umbrales de AOO y EOO.
        return {}

    # ------------------------------------------------------------- manual ops
    def _get_existing_manual_layer(self):
        """Return the current layer for user-added points, or None if it was removed."""
        if _layer_is_usable(self.manual_layer):
            return self.manual_layer

        self.manual_layer = None
        project = QgsProject.instance()

        if self.manual_layer_id:
            layer = project.mapLayer(self.manual_layer_id)
            if _layer_is_usable(layer):
                self.manual_layer = layer
                return layer
            self.manual_layer_id = None

        for layer in project.mapLayers().values():
            try:
                if layer.customProperty("aoo_eoo_gbif_pro_layer_type") == "manual_points" and _layer_is_usable(layer):
                    self.manual_layer = layer
                    self.manual_layer_id = layer.id()
                    return layer
            except RuntimeError:
                continue
        return None

    def _ensure_manual_layer(self):
        layer = self._get_existing_manual_layer()
        if layer is None:
            layer = create_manual_layer()
            layer.setCustomProperty("aoo_eoo_gbif_pro_layer_type", "manual_points")
            QgsProject.instance().addMapLayer(layer)
            self.manual_layer = layer
            self.manual_layer_id = layer.id()
        self.manual_status.setText(f"User points layer active: {_layer_name(layer)}")
        return layer

    def create_manual_points_layer(self):
        layer = self._ensure_manual_layer()
        if self.layer_combo is not None:
            self.layer_combo.setLayer(layer)
        self._log(f"Layer for added points prepared: {_layer_name(layer)}")
        self._check_only_calc_layer(layer)

    def activate_manual_point_tool(self):
        layer = self._ensure_manual_layer()
        if not _layer_is_usable(layer):
            QMessageBox.warning(self, "Added points", "A valid layer for your points could not be created.")
            return
        self.previous_map_tool = self.iface.mapCanvas().mapTool()
        self.manual_tool = ManualPointTool(self.iface.mapCanvas(), self._manual_point_clicked)
        self.iface.mapCanvas().setMapTool(self.manual_tool)
        self._log("Click on the map to add a point. A form will open before saving it.")

    def activate_manual_delete_tool(self):
        layer = self._ensure_manual_layer()
        if not _layer_is_usable(layer):
            QMessageBox.warning(self, "Added points", "No valid user-points layer was found for deletion.")
            return
        self.previous_map_tool = self.iface.mapCanvas().mapTool()
        self.manual_tool = ManualPointTool(self.iface.mapCanvas(), self._manual_delete_clicked)
        self.iface.mapCanvas().setMapTool(self.manual_tool)
        self._log("Haz clic cerca de un punto propio para eliminarlo de la capa.")

    def activate_manual_delete_area_tool(self):
        layer = self._ensure_manual_layer()
        if not _layer_is_usable(layer):
            QMessageBox.warning(self, "Added points", "No valid user-points layer was found for deletion.")
            return
        self.previous_map_tool = self.iface.mapCanvas().mapTool()
        self.manual_tool = ManualRectangleTool(self.iface.mapCanvas(), self._manual_delete_area_selected)
        self.iface.mapCanvas().setMapTool(self.manual_tool)
        self._log("Drag a rectangle on the map to delete the user points contained in that area.")

    def _manual_delete_area_selected(self, rect):
        layer = self._get_existing_manual_layer()
        if not _layer_is_usable(layer):
            QMessageBox.warning(self, "Added points", "The user-points layer does not exist.")
            return
        canvas_crs = self.iface.mapCanvas().mapSettings().destinationCrs()
        target_crs = layer.crs()
        try:
            selection_geom = QgsGeometry.fromRect(rect)
            if canvas_crs != target_crs:
                selection_geom.transform(QgsCoordinateTransform(canvas_crs, target_crs, QgsProject.instance()))
        except Exception as exc:
            QMessageBox.warning(self, "Delete points", f"The selection area could not be transformed: {exc}")
            return

        # If the user only clicks, the rectangle can be nearly empty. Expand it
        # slightly so it still behaves like an easier point-deletion tool.
        try:
            bbox = selection_geom.boundingBox()
            if bbox.width() == 0 and bbox.height() == 0:
                center = bbox.center()
                tol = 0.001 if target_crs.isGeographic() else max(20.0, self.iface.mapCanvas().mapUnitsPerPixel() * 20.0)
                selection_geom = QgsGeometry.fromRect(QgsRectangle(center.x() - tol, center.y() - tol, center.x() + tol, center.y() + tol))
        except (AttributeError, RuntimeError, ValueError) as exc:
            self._log(f"ERROR expanding point-deletion selection: {exc}")
            QMessageBox.warning(self, "Delete points", f"The selection area could not be prepared: {exc}")
            return

        fids = []
        skipped_geometries = 0
        for feat in layer.getFeatures():
            geom = feat.geometry()
            if geom is None or geom.isEmpty():
                continue
            try:
                if selection_geom.intersects(geom):
                    fids.append(feat.id())
            except (RuntimeError, ValueError, TypeError) as exc:
                skipped_geometries += 1
                self._log(f"Skipping feature {feat.id()} during area selection: {exc}")

        if skipped_geometries:
            QMessageBox.warning(
                self, "Delete points",
                f"Could not check {skipped_geometries} feature(s) due to geometry errors. "
                "No points have been deleted. Repair the geometries and retry."
            )
            return
        if not fids:
            QMessageBox.information(self, "Added points", "There are no user points inside the selected area.")
            return

        reply = QMessageBox.question(
            self,
            "Delete points",
            f"Delete {len(fids)} user point(s) inside the selected area?",
            _messagebox_yes() | _messagebox_no(),
            _messagebox_no(),
        )
        if reply != _messagebox_yes():
            return

        was_editing = layer.isEditable()
        if not was_editing:
            layer.startEditing()
        ok = layer.deleteFeatures(fids)
        if not was_editing:
            layer.commitChanges()
        layer.updateExtents()
        layer.triggerRepaint()
        self.iface.mapCanvas().refresh()
        if ok:
            self.refresh_calc_layers(apply_defaults=False)
            self._log(f"User points deleted by area: {len(fids)}")
        else:
            QMessageBox.warning(self, "Added points", "QGIS could not delete the selected points.")

    def _manual_delete_clicked(self, point, button):
        layer = self._get_existing_manual_layer()
        if not _layer_is_usable(layer):
            QMessageBox.warning(self, "Added points", "The user-points layer does not exist.")
            return
        canvas_crs = self.iface.mapCanvas().mapSettings().destinationCrs()
        target_crs = layer.crs()
        click_point = QgsPointXY(point)
        if canvas_crs != target_crs:
            click_point = QgsCoordinateTransform(canvas_crs, target_crs, QgsProject.instance()).transform(click_point)
        click_geom = QgsGeometry.fromPointXY(click_point)
        best_fid = None
        best_dist = None
        skipped_geometries = 0
        for feat in layer.getFeatures():
            geom = feat.geometry()
            if geom is None or geom.isEmpty():
                continue
            try:
                dist = geom.distance(click_geom)
            except (RuntimeError, ValueError, TypeError) as exc:
                skipped_geometries += 1
                self._log(f"Skipping feature {feat.id()} during nearest-point search: {exc}")
            else:
                if best_dist is None or dist < best_dist:
                    best_dist = dist
                    best_fid = feat.id()
        if skipped_geometries:
            QMessageBox.warning(
                self, "Delete point",
                f"Could not check {skipped_geometries} feature(s) due to geometry errors. "
                "No point has been deleted. Repair the geometries and retry."
            )
            return
        # Manual layer is EPSG:4326 by default; 0.0005° is roughly 55 m.
        tol = 0.0005 if target_crs.isGeographic() else max(10.0, self.iface.mapCanvas().mapUnitsPerPixel() * 12.0)
        if best_fid is None or best_dist is None or best_dist > tol:
            QMessageBox.information(self, "Added points", "No user point was found close enough to the click.")
            return
        reply = QMessageBox.question(
            self,
            "Delete point",
            "Delete the user point closest to the click?",
            _messagebox_yes() | _messagebox_no(),
            _messagebox_no(),
        )
        if reply != _messagebox_yes():
            return
        was_editing = layer.isEditable()
        if not was_editing:
            layer.startEditing()
        ok = layer.deleteFeature(best_fid)
        if not was_editing:
            layer.commitChanges()
        layer.updateExtents()
        layer.triggerRepaint()
        if ok:
            self.refresh_calc_layers(apply_defaults=False)
            self._log(f"Punto propio eliminado: feature id {best_fid}")
        else:
            QMessageBox.warning(self, "Added points", "QGIS could not delete the selected point.")

    def stop_manual_point_tool(self):
        if self.previous_map_tool is not None:
            self.iface.mapCanvas().setMapTool(self.previous_map_tool)
        self.manual_tool = None
        self._log("Point-adding mode finished.")

    def _manual_point_clicked(self, point, button):
        layer = self._ensure_manual_layer()
        if not _layer_is_usable(layer):
            QMessageBox.warning(self, "Added points", "The layer for your points no longer exists. Create it again.")
            return
        dialog = ManualFeatureDialog(self, default_name=self.scientific_name.text().strip())
        if _dialog_exec(dialog) == _dialog_accepted():
            canvas_crs = self.iface.mapCanvas().mapSettings().destinationCrs()
            add_manual_feature(layer, point, canvas_crs, dialog.values())
            self._log("Point added to your points layer.")
            self.refresh_calc_layers(apply_defaults=False)
            if not self._selected_calc_layers():
                self._check_only_calc_layer(layer)

    def add_manual_point_by_coordinates(self):
        layer = self._ensure_manual_layer()
        if not _layer_is_usable(layer):
            QMessageBox.warning(self, "Added points", "A valid layer for your points could not be created.")
            return
        dialog = ManualFeatureDialog(self, default_name=self.scientific_name.text().strip(), show_coordinates=True)
        if _dialog_exec(dialog) == _dialog_accepted():
            values = dialog.values()
            lat = values.get("decimalLatitude")
            lon = values.get("decimalLongitude")
            if abs(float(lat)) < 1e-12 and abs(float(lon)) < 1e-12:
                QMessageBox.warning(self, "Coordinates", "Coordinates 0,0 are not valid for this point.")
                return
            add_manual_feature(layer, QgsPointXY(float(lon), float(lat)), QgsCoordinateReferenceSystem("EPSG:4326"), values)
            if self.layer_combo is not None:
                self.layer_combo.setLayer(layer)
            self._log("Point added by coordinates to your points layer.")
            self.refresh_calc_layers(apply_defaults=False)
            if not self._selected_calc_layers():
                self._check_only_calc_layer(layer)

    def _check_only_calc_layer(self, layer):
        """Use the newly imported layer alone; users can check more layers explicitly."""
        self.refresh_calc_layers(apply_defaults=False)
        if self.calc_layers_list is None:
            return
        for i in range(self.calc_layers_list.count()):
            item = self.calc_layers_list.item(i)
            item.setCheckState(
                _qt_checked() if item.data(_qt_user_role()) == layer.id() else _qt_unchecked()
            )
        self._update_calc_selection_summary()

    def import_manual_points_csv(self):
        path, _ = QFileDialog.getOpenFileName(self, "Import point CSV", "", "CSV (*.csv);;All files (*.*)")
        if not path:
            return
        # Never import a CSV into the layer for points added manually.
        name = os.path.splitext(os.path.basename(path))[0].strip() or "imported_csv_points"
        layer = create_manual_layer(f"CSV: {name}")
        if not _layer_is_usable(layer):
            QMessageBox.warning(self, "Import CSV", "A valid independent CSV layer could not be created.")
            return
        try:
            count = import_manual_csv(
                layer, path, default_scientific_name=self.scientific_name.text().strip(),
                default_include=True, default_review="accepted",
            )
            if count == 0:
                raise ValueError("The CSV did not contain any valid latitude/longitude pairs.")
        except (OSError, ValueError, RuntimeError, TypeError) as exc:
            QMessageBox.critical(self, "Error importing CSV", str(exc))
            self._log(f"ERROR CSV: {exc}")
            return
        layer.setCustomProperty("aoo_eoo_gbif_pro_layer_type", "imported_csv")
        layer.setCustomProperty("aoo_eoo_gbif_pro_import_source", path)
        QgsProject.instance().addMapLayer(layer)
        self._check_only_calc_layer(layer)
        self._log(f"Independent CSV layer imported: {_layer_name(layer)} ({count} points). Selected alone in tab 3.")
        try:
            self.iface.setActiveLayer(layer)
        except (AttributeError, RuntimeError, TypeError) as exc:
            self._log(f"CSV layer imported, but QGIS could not activate it: {exc}")

    def import_point_shapefile(self):
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Import point shapefile",
            "",
            "Shapefile (*.shp);;GeoPackage (*.gpkg);;GeoJSON (*.geojson *.json);;Todos los archivos (*.*)",
        )
        if not path:
            return
        name = os.path.splitext(os.path.basename(path))[0] or "puntos_importados"
        layer = QgsVectorLayer(path, name, "ogr")
        if not _layer_is_usable(layer):
            QMessageBox.critical(self, "Import shapefile", "The selected vector layer could not be opened.")
            self._log(f"ERROR shapefile: no se pudo abrir {path}")
            return
        if not self._is_probably_point_layer(layer):
            QMessageBox.warning(
                self,
                "Importar shapefile",
                "La capa seleccionada no parece ser una capa de puntos. Solo se importan capas de puntos o multipuntos.",
            )
            return
        try:
            if layer.featureCount() == 0:
                QMessageBox.warning(self, "Import shapefile", "The selected layer does not contain points.")
                return
        except (RuntimeError, ValueError, TypeError) as exc:
            self._log(f"ERROR reading imported layer feature count: {exc}")
            QMessageBox.warning(self, "Import shapefile", f"Cannot verify the point count: {exc}")
            return
        layer.setCustomProperty("aoo_eoo_gbif_pro_layer_type", "imported_point_file")
        layer.setCustomProperty("aoo_eoo_gbif_pro_import_source", path)
        QgsProject.instance().addMapLayer(layer)
        try:
            self.iface.setActiveLayer(layer)
        except (AttributeError, RuntimeError, TypeError) as exc:
            # The layer is already loaded; activation is a UI convenience.
            self._log(f"Imported layer loaded, but QGIS could not activate it: {exc}")
        self._check_only_calc_layer(layer)
        self._log(f"Point shapefile/vector layer imported: {_layer_name(layer)} ({layer.featureCount()} records). Selected alone in tab 3; additional layers may be checked manually.")
        try:
            self.iface.messageBar().pushSuccess("Import shapefile", f"Point layer imported: {_layer_name(layer)}")
        except (AttributeError, RuntimeError, TypeError) as exc:
            # Nonessential UI notification; the import and log already succeeded.
            self._log(f"QGIS could not display the import success notification: {exc}")

    def save_manual_csv_template(self):
        default_name = "IUCN_Red_List_calculator_plantilla_puntos_propios.csv"
        path, _ = QFileDialog.getSaveFileName(self, "Save base CSV template", default_name, "CSV (*.csv)")
        if not path:
            return
        if not path.lower().endswith(".csv"):
            path += ".csv"
        header = [
            "scientificName", "decimalLatitude", "decimalLongitude", "eventDate",
            "data_citation", "data_origin", "data_curator", "evidence", "identifier",
            "coordinateUncertaintyInMeters", "review_status", "include_for_aoo_eoo", "notes"
        ]
        try:
            with open(path, "w", encoding="utf-8-sig", newline="") as handle:
                handle.write(",".join(header) + "\n")
            self._log(f"CSV template saved: {path}")
            try:
                self.iface.messageBar().pushSuccess("CSV template", "Empty CSV template saved.")
            except (AttributeError, RuntimeError, TypeError) as exc:
                # Saving succeeded; only the optional QGIS message bar failed.
                self._log(f"QGIS could not display the CSV success notification: {exc}")
        except OSError as exc:
            QMessageBox.critical(self, "Error al guardar plantilla", str(exc))
            self._log(f"ERROR plantilla CSV: {exc}")


    # ----------------------------------------------------------- Point Distribution CSV
    def _ensure_last_result(self):
        if self.last_result is None:
            QMessageBox.warning(self, "Point Distribution", "First calculate AOO/EOO. The CSV is generated from the points used in that calculation.")
            return None
        return self.last_result

    def _point_distribution_settings(self):
        dialog = PointDistributionSettingsDialog(self, default_name=self.scientific_name.text().strip(), default_subspecies=(self.infraspecific_epithet.text().strip() if self.assess_infraspecific.isChecked() else ""))
        if _dialog_exec(dialog) == _dialog_accepted():
            return dialog.values()
        return None

    def create_iucn_polygon_field_guide(self):
        try:
            layer = create_iucn_polygon_field_guide_layer()
            QgsProject.instance().addMapLayer(layer)
            self._log("Help table added: IUCN AOO/EOO attribute fields")
            self.iface.messageBar().pushSuccess("AOO/EOO", "IUCN attribute help table for AOO/EOO added to the project.")
        except Exception as exc:  # pylint: disable=broad-except
            QMessageBox.critical(self, "AOO/EOO", str(exc))
            self._log(f"ERROR ayuda IUCN AOO/EOO: {exc}")

    def create_point_distribution_table(self):
        result = self._ensure_last_result()
        if result is None:
            return
        settings = self._point_distribution_settings()
        if settings is None:
            return
        try:
            layer = create_point_distribution_layer(result, settings)
            QgsProject.instance().addMapLayer(layer)
            self.point_distribution_layer = layer
            self._log(f"Point Distribution table added to the project: {layer.featureCount()} rows.")
            self.iface.messageBar().pushSuccess("Point Distribution", "Point Distribution table added to the QGIS project.")
        except Exception as exc:  # pylint: disable=broad-except
            QMessageBox.critical(self, "Point Distribution", str(exc))
            self._log(f"ERROR Point Distribution: {exc}")

    def save_point_distribution_csv(self):
        result = self._ensure_last_result()
        if result is None:
            return
        settings = self._point_distribution_settings()
        if settings is None:
            return
        path, _ = QFileDialog.getSaveFileName(self, "Save Point Distribution CSV", "point_distribution.csv", "CSV (*.csv)")
        if not path:
            return
        if not path.lower().endswith(".csv"):
            path += ".csv"
        try:
            count = write_point_distribution_csv(result, settings, path)
            self._log(f"CSV Point Distribution guardado: {path} ({count} filas)")
            self.iface.messageBar().pushSuccess("Point Distribution", f"CSV guardado con {count} filas.")
        except Exception as exc:  # pylint: disable=broad-except
            QMessageBox.critical(self, "Point Distribution", str(exc))
            self._log(f"ERROR al guardar CSV Point Distribution: {exc}")

    def create_point_distribution_shapefile_layer(self):
        result = self._ensure_last_result()
        if result is None:
            return
        settings = self._point_distribution_settings()
        if settings is None:
            return
        try:
            layer = create_point_distribution_shapefile_layer(result, settings)
            QgsProject.instance().addMapLayer(layer)
            self._log(f"Point Distribution layer added to the project: {layer.featureCount()} points.")
            self.iface.messageBar().pushSuccess("Point Distribution", "Point Distribution layer added to the QGIS project.")
        except Exception as exc:  # pylint: disable=broad-except
            QMessageBox.critical(self, "Point Distribution", str(exc))
            self._log(f"ERROR Point Distribution layer: {exc}")

    def save_point_distribution_shapefile(self):
        result = self._ensure_last_result()
        if result is None:
            return
        settings = self._point_distribution_settings()
        if settings is None:
            return
        path, _ = QFileDialog.getSaveFileName(self, "Save Point Distribution shapefile", "point_distribution.shp", "Shapefile (*.shp)")
        if not path:
            return
        if not path.lower().endswith(".shp"):
            path += ".shp"
        try:
            count = write_point_distribution_shapefile(result, settings, path)
            self._log(f"Point Distribution shapefile saved: {path} ({count} points)")
            self.iface.messageBar().pushSuccess("Point Distribution", f"Shapefile saved with {count} points.")
        except Exception as exc:  # pylint: disable=broad-except
            QMessageBox.critical(self, "Point Distribution", str(exc))
            self._log(f"ERROR al guardar Shapefile Point Distribution: {exc}")

    # ----------------------------------------------------------- GBIF DOI
    def _gbif_ids_from_result(self, result):
        ids = []
        seen = set()
        manual_or_non_gbif = 0
        missing_gbif_id = 0
        for rec in (result or {}).get("used_records", []):
            origin = (rec.get("data_origin") or rec.get("origin") or "").strip().upper()
            gbif_id = str(rec.get("gbifID") or "").strip()
            if gbif_id:
                if gbif_id not in seen:
                    ids.append(gbif_id)
                    seen.add(gbif_id)
            else:
                if origin == "GBIF":
                    missing_gbif_id += 1
                else:
                    manual_or_non_gbif += 1
        return ids, manual_or_non_gbif, missing_gbif_id

    def _gbif_ids_for_download(self):
        result = self._ensure_last_result()
        if result is None:
            return None
        ids, manual_count, missing_count = self._gbif_ids_from_result(result)
        if not ids:
            QMessageBox.warning(
                self,
                "Cita GBIF",
                "There are no gbifIDs in the points used. An official GBIF DOI can only be generated for GBIF records with gbifID."
            )
            return None
        return ids, manual_count, missing_count

    def _gbif_ids_preview_text(self, result):
        ids, manual_count, missing_count = self._gbif_ids_from_result(result)
        preview_ids = "\n".join(ids[:250])
        if len(ids) > 250:
            preview_ids += f"\n... ({len(ids) - 250} gbifID más)"
        return (
            f"Registros GBIF con gbifID usados en el cálculo: {len(ids)}\n"
            f"Puntos propios/no GBIF usados: {manual_count}\n"
            f"Registros GBIF usados sin gbifID: {missing_count}\n\n"
            "Lista gbifID que se enviará a GBIF para crear la descarga oficial:\n"
            f"{preview_ids if preview_ids else '[sin gbifID]'}\n\n"
            "You do not need to paste this list into any website if you use the ‘Request official download and DOI’ button. "
            "The plugin will send it to GBIF through the download API. Copying to the clipboard is only for review or archiving."
        )

    def _refresh_gbif_doi_tab(self):
        if self.last_result is not None and hasattr(self, "gbif_download_result"):
            self.gbif_download_result.setPlainText(self._gbif_ids_preview_text(self.last_result))

    def prepare_gbif_download_ids(self):
        result = self._ensure_last_result()
        if result is None:
            return
        ids_info = self._gbif_ids_for_download()
        if ids_info is None:
            return
        self.gbif_download_result.setPlainText(self._gbif_ids_preview_text(result))
        ids, manual_count, missing_count = ids_info
        self._log(f"Prepared {len(ids)} gbifIDs for the official GBIF download. Non-GBIF points: {manual_count}; GBIF without gbifID: {missing_count}.")
        self.iface.messageBar().pushSuccess("GBIF citation", f"Prepared {len(ids)} gbifIDs to request an official DOI from GBIF.")

    def copy_gbif_ids(self):
        ids_info = self._gbif_ids_for_download()
        if ids_info is None:
            return
        ids, _, _ = ids_info
        QApplication.clipboard().setText("\n".join(ids))
        self._log("Used gbifIDs copied to the clipboard.")
        self.iface.messageBar().pushSuccess("Cita GBIF", "gbifID copiados al portapapeles.")

    def request_gbif_occurrence_download(self):
        ids_info = self._gbif_ids_for_download()
        if ids_info is None:
            return
        ids, manual_count, missing_count = ids_info
        username = self.gbif_download_user.text().strip()
        password = self.gbif_download_password.text()
        email = self.gbif_download_email.text().strip()
        fmt = self.gbif_download_format.currentData() or "SIMPLE_CSV"
        missing = []
        if not username:
            missing.append("GBIF username")
        if not password:
            missing.append("GBIF password")
        if missing:
            QMessageBox.warning(self, "GBIF citation", "Missing fields: " + ", ".join(missing))
            return
        if "@" in username:
            QMessageBox.warning(
                self,
                "Cita GBIF",
                "En ‘Usuario GBIF’ debes escribir el nombre de usuario de GBIF, no el correo electrónico.\n\n"
                "Ejemplo correcto: nombre_usuario_gbif\n"
                "The email address should be entered only in ‘Notification email’."
            )
            return

        if manual_count or missing_count:
            note = (
                f"Se solicitará el DOI solo para {len(ids)} registros GBIF con gbifID.\n"
                f"Puntos propios/no GBIF usados: {manual_count}.\n"
                f"Registros GBIF usados sin gbifID: {missing_count}.\n\n"
                "Those points will not be covered by the GBIF DOI. Continue?"
            )
            confirm = QMessageBox.question(self, "Cita GBIF", note)
            try:
                yes_value = QMessageBox.Yes
            except AttributeError:
                yes_value = QMessageBox.StandardButton.Yes
            if confirm != yes_value:
                return

        try:
            key = request_occurrence_download_by_gbif_ids(
                ids,
                username=username,
                password=password,
                notification_email=email or None,
                download_format=fmt,
            )
            self.gbif_download_key = key
            self.gbif_download_key_edit.setText(key)
            self.gbif_download_result.setPlainText(
                "Solicitud enviada a GBIF.\n\n"
                f"Clave de descarga: {key}\n"
                f"Registros GBIF solicitados: {len(ids)}\n"
                f"Formato: {fmt}\n\n"
                "The DOI may not yet exist. Press ‘Check status / DOI’ again in a few minutes. "
                "GBIF will also send an email if you provided a notification address."
            )
            self._log(f"Official GBIF download requested. Key: {key}")
            self.iface.messageBar().pushSuccess("Cita GBIF", f"Solicitud enviada. Clave GBIF: {key}")
        except Exception as exc:  # pylint: disable=broad-except
            QMessageBox.critical(self, "Cita GBIF", str(exc))
            self._log(f"ERROR requesting GBIF download: {exc}")

    def _citation_from_gbif_download(self, response: dict) -> str:
        citation = (response or {}).get("citation") or ""
        if citation:
            return citation
        doi = (response or {}).get("doi") or ""
        if doi:
            doi_text = str(doi).strip()
            doi_url = doi_text if doi_text.startswith("http") else f"https://doi.org/{doi_text}"
            year = datetime.now().year
            return f"GBIF.org ({year}). GBIF Occurrence Download. {doi_url}"
        return ""

    def check_gbif_occurrence_download(self):
        key = self.gbif_download_key_edit.text().strip() or self.gbif_download_key
        if not key:
            QMessageBox.warning(self, "GBIF citation", "Enter or request a GBIF download key first.")
            return
        try:
            response = get_occurrence_download(key)
            self.gbif_download_key = key
            self.gbif_download_response = response
            status = response.get("status", "")
            doi = response.get("doi", "")
            citation = self._citation_from_gbif_download(response)
            download_link = response.get("downloadLink") or response.get("downloadUrl") or ""
            if doi:
                doi_text = str(doi).strip()
                doi_url = doi_text if doi_text.startswith("http") else f"https://doi.org/{doi_text}"
            else:
                doi_url = "[not yet available]"
            result_text = (
                "Estado de la descarga GBIF\n\n"
                f"Clave: {key}\n"
                f"Estado: {status}\n"
                f"DOI: {doi_url}\n"
                f"Registros en la descarga: {response.get('numberRecords', '')}\n"
                f"Enlace de descarga: {download_link}\n\n"
                "Cita recomendada:\n"
                f"{citation if citation else '[todavía no disponible; espera a que el estado sea SUCCEEDED]'}\n\n"
                "Remember: this citation covers only the GBIF records included in the official download."
            )
            self.gbif_download_result.setPlainText(result_text)
            if status == "SUCCEEDED" or doi:
                layer = create_gbif_occurrence_download_result_layer(response)
                QgsProject.instance().addMapLayer(layer)
                self.gbif_doi_layer = layer
                self.iface.messageBar().pushSuccess("GBIF citation", "GBIF DOI ready and table added to the project.")
            else:
                self.iface.messageBar().pushMessage("Cita GBIF", f"Estado actual: {status}", level=Qgis.Info, duration=6)
            self._log(f"GBIF download status {key}: {status}; DOI: {doi}")
        except Exception as exc:  # pylint: disable=broad-except
            QMessageBox.critical(self, "Cita GBIF", str(exc))
            self._log(f"ERROR checking GBIF download: {exc}")

    def copy_gbif_citation(self):
        text = self.gbif_download_result.toPlainText() if hasattr(self, "gbif_download_result") else ""
        citation = ""
        if self.gbif_download_response:
            citation = self._citation_from_gbif_download(self.gbif_download_response)
        if not citation and "Recommended citation:" in text:
            citation = text.split("Cita recomendada:", 1)[1].strip().split("\n\n", 1)[0].strip()
        if not citation or citation.startswith("["):
            QMessageBox.warning(self, "GBIF citation", "There is no citation available yet. Check the status until GBIF returns the DOI.")
            return
        QApplication.clipboard().setText(citation)
        self.iface.messageBar().pushSuccess("Cita GBIF", "Cita GBIF copiada al portapapeles.")
        self._log("Cita GBIF copiada al portapapeles.")

    def _iucn_polygon_attrs(self) -> dict:
        return {
            "sci_name": self.scientific_name.text().strip(),
            "presence": self.iucn_presence.currentData(),
            "origin": self.iucn_origin.currentData(),
            "seasonal": self.iucn_seasonal.currentData(),
            "compiler": self.iucn_compiler.text().strip(),
            "yrcompiled": self.iucn_yrcompiled.value(),
            "citation": self.iucn_citation.text().strip(),
            "subspecies": self.iucn_subspecies.text().strip() or (self.infraspecific_epithet.text().strip() if self.assess_infraspecific.isChecked() else ""),
            "subpop": "",
            "data_sens": self.iucn_data_sens.currentData(),
            "sens_comm": self.iucn_sens_comm.text().strip(),
        }

    # --------------------------------------------------------------- calculate

    def _analysis_crs_authid(self) -> str:
        """Return a valid-looking EPSG authid from the CRS combo box.

        The combo box is editable: selected entries store the EPSG code as item data,
        while manually typed values are parsed from the visible text.
        """
        try:
            data = self.analysis_crs.currentData()
            if data:
                return str(data).strip()
        except (AttributeError, RuntimeError, TypeError) as exc:
            # Editable combo boxes may lack item data; read the visible text.
            self._log(f"CRS item data unavailable; reading the CRS text instead: {exc}")
        try:
            raw_text = self.analysis_crs.currentText().strip()
        except Exception:
            raw_text = ""
        match = re.search(r"EPSG\s*[:=]\s*(\d+)", raw_text, flags=re.IGNORECASE)
        if match:
            return f"EPSG:{match.group(1)}"
        if raw_text.isdigit():
            return f"EPSG:{raw_text}"
        return raw_text

    def calculate(self):
        self.refresh_calc_layers(apply_defaults=False)
        layers = self._selected_calc_layers()

        if not layers:
            QMessageBox.warning(self, "Calculation", "Check one or more point layers in the list in tab 3 before calculating.")
            return

        layer_description = "; ".join(
            f"{_layer_name(layer)} ({layer.featureCount()} records)" for layer in layers
        )
        if len(layers) > 1:
            # Both buttons exist in QGIS 3 (Qt5) and QGIS 4 (Qt6).
            yes = getattr(QMessageBox, "Yes", None)
            no = getattr(QMessageBox, "No", None)
            if yes is None:
                yes = QMessageBox.StandardButton.Yes
                no = QMessageBox.StandardButton.No
            reply = QMessageBox.question(
                self, "Confirm combined layers / Confirmar capas combinadas",
                "The following layers will be COMBINED for this calculation:\n"
                f"{layer_description}\n\n"
                "Are they all intentional inputs? / ¿Quieres combinar todas estas capas?",
                yes | no, no,
            )
            if reply != yes:
                self._log("Combined-layer calculation cancelled; the selected layers were not changed.")
                return
        if abs(self.cell_size.value() - 2000) > 0.001:
            yes = getattr(QMessageBox, "Yes", None)
            no = getattr(QMessageBox, "No", None)
            if yes is None:
                yes = QMessageBox.StandardButton.Yes
                no = QMessageBox.StandardButton.No
            reply = QMessageBox.question(
                self, "Nonstandard AOO grid / Cuadrícula AOO no estándar",
                f"AOO cell size: {self.cell_size.value():g} m. "
                "The IUCN reference size is 2000 m (2 × 2 km).\n"
                "Continue with your custom size? / ¿Continuar con ese tamaño personalizado?",
                yes | no, no,
            )
            if reply != yes:
                self._log("Calculation cancelled to review the AOO grid size.")
                return
        self._log("Layers sent to the calculation: " + layer_description)
        max_uncert = self.max_uncertainty.value() if self.use_uncertainty_filter.isChecked() else None
        try:
            result = run_aoo_eoo(
                layers,
                analysis_crs_authid=self._analysis_crs_authid(),
                cell_size_m=self.cell_size.value(),
                max_uncertainty_m=max_uncert,
                include_pending_manual=self.include_pending.isChecked(),
                deduplicate=self.deduplicate.isChecked(),
                iucn_polygon_attrs=self._iucn_polygon_attrs(),
                iucn_b_inputs=self._iucn_criterion_b_inputs(),
            )
            QgsProject.instance().addMapLayer(result["used_layer"])
            QgsProject.instance().addMapLayer(result["aoo_layer"])
            if result["eoo_layer"] is not None:
                QgsProject.instance().addMapLayer(result["eoo_layer"])

            result["taxon_name"] = self.scientific_name.text().strip()
            result["taxon_key"] = self.taxon_key.text().strip()
            try:
                result["gbif_query_params"] = self._build_gbif_params()
            except Exception:
                result["gbif_query_params"] = {}
            self.last_result = result
            self._refresh_gbif_doi_tab()
            report_layers = create_report_layers(result)
            for layer in report_layers.values():
                QgsProject.instance().addMapLayer(layer)
            self._log("Calculation finished. Layers and tables added to the QGIS project.")
            self._log(f"  Used records: {result['n_used']}")
            self._log(f"  Registros excluidos: {result['n_excluded']}")
            self._log(f"  Celdas AOO ocupadas: {result['n_cells']}")
            self._log(f"  AOO: {result['aoo_km2']:.2f} km²")
            self._log(f"  EOO: {result['eoo_km2']:.2f} km²")
            iucn_b = result.get("iucn_criterion_b", {})
            if iucn_b:
                self._log(f"  Indicative category by AOO: {iucn_b.get('aoo_category', 'Not evaluable')}")
                self._log(f"  Indicative category by EOO: {iucn_b.get('eoo_category', 'Not evaluable')}")
            self._log("  Table added: AOO_EOO report summary")
            self._log("  Tab 5 updated with the gbifIDs used to request the official GBIF DOI")
            self._log("  Table added: AOO_EOO unused records")
            self.iface.messageBar().pushSuccess("AOO/EOO", "Calculation finished. The final layers and report tables are in the Layers panel.")
        except Exception as exc:  # pylint: disable=broad-except
            QMessageBox.critical(self, "AOO/EOO calculation error", str(exc))
            self._log(f"ERROR calculation: {exc}")
