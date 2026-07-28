from qgis.PyQt.QtWidgets import (
    QDockWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QStackedWidget, QWidget, QCheckBox, QMessageBox, QLineEdit, QComboBox
)
from qgis.gui import QgsFileWidget
from qgis.core import QgsProject, QgsRasterLayer, QgsVectorLayer, QgsApplication
from qgis.PyQt.QtCore import pyqtSignal, QDate
from qgis.gui import QgsDateEdit

from .settings_dialog import SettingsDialog, credentials_are_saved
from .threshold_widget import ThresholdRow
from .export_worker import ClassificationTask


THRESHOLD_PROFILES = {
    'plain': {
        'ndsi': ('>', 0.22),
        'nir_floor_snow': ('>', 0.12),
        'mndwi': ('>', 0),
        'water_ndvi': ('<', 0),
        'veg_ndvi': ('>', 0.35),
        'veg_ndre': ('>', 0),
        'builtup_ndbi': ('>', 0),
        'builtup_bsi': ('<', 0.15),
        'baresoil_ndbi': ('>', -0.05),
        'baresoil_bsi_low': ('>', 0.15),
        'baresoil_bsi_high': ('<', 0.49),
    },
    'high_elevation': {
        'ndsi': ('>', 0.22),
        'nir_floor_snow': ('>', 0.12),
        'mndwi': ('>', -0.1),
        'water_ndvi': ('<', 0.02),
        'veg_ndvi': ('>', 0.35),
        'veg_ndre': ('>', 0),
        'builtup_ndbi': ('>', 0.02),
        'builtup_bsi': ('<', 0.12),
        'baresoil_ndbi': ('>', -0.05),
        'baresoil_bsi_low': ('>', 0.12),
        'baresoil_bsi_high': ('<', 0.49),
    },
}

DEFAULT_CLOUD_COVER = 20


class MainDockWidget(QDockWidget):
    progress_signal = pyqtSignal(str)
    finished_signal = pyqtSignal(bool, str, object)

    def __init__(self, iface):
        super().__init__("LULC Classifier")
        self.iface = iface
        self.task = None
        self.stage = 'input'

        container = QWidget()
        main_layout = QVBoxLayout()

        self.stack = QStackedWidget()
        self.page_inputs = self._build_input_page()
        self.page_thresholds = self._build_threshold_page()
        self.stack.addWidget(self.page_inputs)
        self.stack.addWidget(self.page_thresholds)
        main_layout.addWidget(self.stack)

        self.progress_label = QLabel("")
        main_layout.addWidget(self.progress_label)

        # ---------- Persistent button bar ----------
        btn_layout = QHBoxLayout()
        self.settings_btn = QPushButton("Settings")
        self.settings_btn.clicked.connect(self._open_settings)
        btn_layout.addWidget(self.settings_btn)

        self.back_btn = QPushButton("Back")
        self.back_btn.clicked.connect(self._go_back)
        btn_layout.addWidget(self.back_btn)

        self.next_btn = QPushButton("Next")
        self.next_btn.clicked.connect(self._go_to_thresholds)
        btn_layout.addWidget(self.next_btn)

        self.run_btn = QPushButton("Run")
        self.run_btn.clicked.connect(self._run_preview)
        btn_layout.addWidget(self.run_btn)

        self.export_btn = QPushButton("Export")
        self.export_btn.clicked.connect(self._run_export)
        btn_layout.addWidget(self.export_btn)

        self.edit_inputs_btn = QPushButton("Edit Inputs")
        self.edit_inputs_btn.clicked.connect(self._edit_inputs)
        btn_layout.addWidget(self.edit_inputs_btn)

        main_layout.addLayout(btn_layout)
        container.setLayout(main_layout)
        self.setWidget(container)

        self.progress_signal.connect(self._update_progress_label)
        self.finished_signal.connect(self._on_task_finished)

        self._apply_stage_state()

    # ---------- Stage/button state management ----------
    def _apply_stage_state(self):
        """Single source of truth for what's clickable at each stage."""
        if self.stage == 'input':
            self.stack.setCurrentIndex(0)
            self.settings_btn.setEnabled(True)
            self.back_btn.setEnabled(False)
            self.next_btn.setEnabled(True)
            self.run_btn.setEnabled(False)
            self.export_btn.setEnabled(False)
            self.edit_inputs_btn.setEnabled(False)
            self._set_input_fields_enabled(True)

        elif self.stage == 'threshold':
            self.stack.setCurrentIndex(1)
            self.settings_btn.setEnabled(True)
            self.back_btn.setEnabled(True)
            self.next_btn.setEnabled(False)
            self.run_btn.setEnabled(True)
            self.export_btn.setEnabled(False)
            self.edit_inputs_btn.setEnabled(False)
            self._set_threshold_fields_enabled(True)

        elif self.stage == 'processing':
            self.settings_btn.setEnabled(False)
            self.back_btn.setEnabled(False)
            self.next_btn.setEnabled(False)
            self.run_btn.setEnabled(False)
            self.export_btn.setEnabled(False)
            self.edit_inputs_btn.setEnabled(False)
            self._set_input_fields_enabled(False)
            self._set_threshold_fields_enabled(False)

        elif self.stage == 'preview_ready':
            self.settings_btn.setEnabled(False)
            self.back_btn.setEnabled(False)
            self.next_btn.setEnabled(False)
            self.run_btn.setEnabled(False)
            self.export_btn.setEnabled(True)
            self.edit_inputs_btn.setEnabled(True)
            self._set_input_fields_enabled(False)
            self._set_threshold_fields_enabled(False)

    def _set_input_fields_enabled(self, enabled):
        self.shp_widget.setEnabled(enabled)
        self.output_widget.setEnabled(enabled)
        self.start_date_widget.setEnabled(enabled)
        self.end_date_widget.setEnabled(enabled)
        self.cloud_cover_input.setEnabled(enabled)

    def _set_threshold_fields_enabled(self, enabled):
        self.terrain_dropdown.setEnabled(enabled)
        self.use_default_checkbox.setEnabled(enabled)
        editable_rows = enabled and not self.use_default_checkbox.isChecked()
        for row in self.threshold_rows.values():
            row.set_editable(editable_rows)

    # ---------- Page 1: Inputs ----------
    def _build_input_page(self):
        page = QWidget()
        layout = QVBoxLayout()

        layout.addWidget(QLabel("Input shapefile (must be in WGS84):"))
        self.shp_widget = QgsFileWidget()
        self.shp_widget.setFilter("Shapefiles (*.shp)")
        layout.addWidget(self.shp_widget)

        layout.addWidget(QLabel("Output folder (where the exported shapefile will be saved):"))
        self.output_widget = QgsFileWidget()
        self.output_widget.setStorageMode(QgsFileWidget.GetDirectory)
        layout.addWidget(self.output_widget)

        layout.addWidget(QLabel("Sentinel 2 composite start date:"))
        self.start_date_widget = QgsDateEdit()
        self.start_date_widget.setDate(QDate(2024, 1, 1))
        layout.addWidget(self.start_date_widget)

        layout.addWidget(QLabel("Sentinel 2 composite end date:"))
        self.end_date_widget = QgsDateEdit()
        self.end_date_widget.setDate(QDate(2024, 6, 30))
        layout.addWidget(self.end_date_widget)

        layout.addWidget(QLabel("Max cloud cover for composite (e.g. 20):"))
        self.cloud_cover_input = QLineEdit(str(DEFAULT_CLOUD_COVER))
        layout.addWidget(self.cloud_cover_input)

        page.setLayout(layout)
        return page

    def _open_settings(self):
        dlg = SettingsDialog()
        dlg.exec_()

    def _go_to_thresholds(self):
        if not credentials_are_saved():
            QMessageBox.warning(
                self, "Settings Required",
                "Please fill in your GEE settings first using the Settings button."
            )
            return
        if not self.shp_widget.filePath():
            QMessageBox.warning(self, "Missing Input", "Please select a study area shapefile.")
            return
        if not self.output_widget.filePath():
            QMessageBox.warning(self, "Missing Output", "Please select an output folder.")
            return
        self.stage = 'threshold'
        self._apply_stage_state()

    def _go_back(self):
        self.stage = 'input'
        self._apply_stage_state()

    # ---------- Page 2: Thresholds ----------
    def _build_threshold_page(self):
        page = QWidget()
        layout = QVBoxLayout()

        layout.addWidget(QLabel("Terrain type:"))
        self.terrain_dropdown = QComboBox()
        self.terrain_dropdown.addItems(["Plain / Slightly Hilly", "High Elevation"])
        self.terrain_dropdown.currentIndexChanged.connect(self._on_terrain_changed)
        layout.addWidget(self.terrain_dropdown)

        self.use_default_checkbox = QCheckBox("Use default values")
        self.use_default_checkbox.setChecked(True)
        self.use_default_checkbox.stateChanged.connect(self._toggle_threshold_editing)
        layout.addWidget(self.use_default_checkbox)

        self.threshold_rows = {}
        layout.addWidget(QLabel("Snow mask:"))
        self.threshold_rows['ndsi'] = ThresholdRow("NDSI", *THRESHOLD_PROFILES['plain']['ndsi'])
        layout.addWidget(self.threshold_rows['ndsi'])
        self.threshold_rows['nir_floor_snow'] = ThresholdRow("NIR (brightness floor)", *THRESHOLD_PROFILES['plain']['nir_floor_snow'])
        layout.addWidget(self.threshold_rows['nir_floor_snow'])

        layout.addWidget(QLabel("Water mask:"))
        self.threshold_rows['mndwi'] = ThresholdRow("MNDWI", *THRESHOLD_PROFILES['plain']['mndwi'])
        layout.addWidget(self.threshold_rows['mndwi'])
        self.threshold_rows['water_ndvi'] = ThresholdRow("NDVI (verification)", *THRESHOLD_PROFILES['plain']['water_ndvi'])
        layout.addWidget(self.threshold_rows['water_ndvi'])

        layout.addWidget(QLabel("Vegetation mask:"))
        self.threshold_rows['veg_ndvi'] = ThresholdRow("NDVI", *THRESHOLD_PROFILES['plain']['veg_ndvi'])
        layout.addWidget(self.threshold_rows['veg_ndvi'])
        self.threshold_rows['veg_ndre'] = ThresholdRow("NDRE", *THRESHOLD_PROFILES['plain']['veg_ndre'])
        layout.addWidget(self.threshold_rows['veg_ndre'])

        layout.addWidget(QLabel("Built-up mask:"))
        self.threshold_rows['builtup_ndbi'] = ThresholdRow("NDBI", *THRESHOLD_PROFILES['plain']['builtup_ndbi'])
        layout.addWidget(self.threshold_rows['builtup_ndbi'])
        self.threshold_rows['builtup_bsi'] = ThresholdRow("BSI", *THRESHOLD_PROFILES['plain']['builtup_bsi'])
        layout.addWidget(self.threshold_rows['builtup_bsi'])

        layout.addWidget(QLabel("Bare soil mask:"))
        self.threshold_rows['baresoil_ndbi'] = ThresholdRow("NDBI", *THRESHOLD_PROFILES['plain']['baresoil_ndbi'])
        layout.addWidget(self.threshold_rows['baresoil_ndbi'])
        self.threshold_rows['baresoil_bsi_low'] = ThresholdRow("BSI (lower)", *THRESHOLD_PROFILES['plain']['baresoil_bsi_low'])
        layout.addWidget(self.threshold_rows['baresoil_bsi_low'])
        self.threshold_rows['baresoil_bsi_high'] = ThresholdRow("BSI (upper)", *THRESHOLD_PROFILES['plain']['baresoil_bsi_high'])
        layout.addWidget(self.threshold_rows['baresoil_bsi_high'])

        page.setLayout(layout)
        return page

    def _toggle_threshold_editing(self):
        editable = not self.use_default_checkbox.isChecked()
        for row in self.threshold_rows.values():
            row.set_editable(editable)

    def _get_current_terrain_key(self):
        return 'plain' if self.terrain_dropdown.currentIndex() == 0 else 'high_elevation'

    def _on_terrain_changed(self):
        profile = THRESHOLD_PROFILES[self._get_current_terrain_key()]
        for key, row in self.threshold_rows.items():
            row.default_operator = profile[key][0]
            row.default_value = profile[key][1]
            if self.use_default_checkbox.isChecked():
                row.set_editable(False)

    def _collect_thresholds(self):
        result = {}
        for key, row in self.threshold_rows.items():
            result[key] = (row.get_operator(), row.get_value())
        return result

    # ---------- Running ----------
    def _get_aoi(self):
        from .gee_processor import shapefile_to_ee_geometry
        return shapefile_to_ee_geometry(self.shp_widget.filePath())

    def _authenticate_ee(self):
        import ee
        from qgis.core import QgsSettings
        settings = QgsSettings()
        email = settings.value("lulc_plugin/service_account", "")
        key_path = settings.value("lulc_plugin/key_path", "")
        credentials = ee.ServiceAccountCredentials(email, key_path)
        ee.Initialize(credentials)

    def _get_key_path(self):
        from qgis.core import QgsSettings
        return QgsSettings().value("lulc_plugin/key_path", "")

    def _run_preview(self):
        self.stage = 'processing'
        self._apply_stage_state()
        self.progress_label.setText("Starting...")
        self._authenticate_ee()

        aoi = self._get_aoi()
        start_date = self.start_date_widget.date().toString("yyyy-MM-dd")
        end_date = self.end_date_widget.date().toString("yyyy-MM-dd")
        thresholds = self._collect_thresholds()
        cloud_cover = float(self.cloud_cover_input.text())
        terrain_type = self._get_current_terrain_key()

        self.task = ClassificationTask(
            aoi, start_date, end_date, cloud_cover, terrain_type, thresholds,
            self.output_widget.filePath(),
            self.progress_signal, self.finished_signal,
            mode='preview'
        )
        QgsApplication.taskManager().addTask(self.task)

    def _run_export(self):
        self.stage = 'processing'
        self._apply_stage_state()
        self.progress_label.setText("Calculating vector export...")

        aoi = self._get_aoi()
        start_date = self.start_date_widget.date().toString("yyyy-MM-dd")
        end_date = self.end_date_widget.date().toString("yyyy-MM-dd")
        thresholds = self._collect_thresholds()
        cloud_cover = float(self.cloud_cover_input.text())
        terrain_type = self._get_current_terrain_key()

        self.task = ClassificationTask(
            aoi, start_date, end_date, cloud_cover, terrain_type, thresholds,
            self.output_widget.filePath(),
            self.progress_signal, self.finished_signal,
            mode='export'
        )
        QgsApplication.taskManager().addTask(self.task)

    def _edit_inputs(self):
        self.stage = 'input'
        self._apply_stage_state()

    def _update_progress_label(self, message):
        self.progress_label.setText(message)

    def _add_xyz_layer(self, url, name):
        uri = f"type=xyz&url={url.replace('&', '%26')}&zmax=19&zmin=0"
        layer = QgsRasterLayer(uri, name, "wms")
        if layer.isValid():
            QgsProject.instance().addMapLayer(layer)

    def _on_task_finished(self, success, error, result_data):
        if not success:
            QMessageBox.critical(self, "Error", f"Something went wrong:\n{error}")
            # Return to whichever stage makes sense to retry from
            self.stage = 'threshold'
            self._apply_stage_state()
            return

        if self.task.mode == 'preview':
            tiles = result_data
            self._add_xyz_layer(tiles['composite'], "Sentinel-2 Composite")
            self._add_xyz_layer(tiles['snow'], "Snow Mask")
            self._add_xyz_layer(tiles['water'], "Water Mask")
            self._add_xyz_layer(tiles['vegetation'], "Vegetation Mask")
            self._add_xyz_layer(tiles['builtup'], "Built-up Mask")
            self._add_xyz_layer(tiles['baresoil'], "Bare Soil Mask")

            self.progress_label.setText("Preview ready. Inspect the layers, then choose Export or Edit Inputs.")
            self.stage = 'preview_ready'
            self._apply_stage_state()

        else:  # export mode finished
            tif_path = result_data
            layer = QgsRasterLayer(tif_path, "LULC Classification")
            if layer.isValid():
                QgsProject.instance().addMapLayer(layer)
                QMessageBox.information(self, "Success", "Export complete and loaded into QGIS.")
            else:
                QMessageBox.critical(self, "Error", "Downloaded raster could not be loaded.")

            self.stage = 'preview_ready'  # allow re-export or edit inputs again
            self._apply_stage_state()