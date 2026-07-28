import time
import datetime
import os
import zipfile
import urllib.request
import ee
from qgis.core import QgsTask, QgsProject, QgsVectorLayer


class ClassificationTask(QgsTask):
    def __init__(self, aoi, start_date, end_date, cloud_cover_pct, terrain_type, thresholds, output_folder,
                progress_signal, finished_signal, mode='preview'):
        super().__init__("LULC Classification", QgsTask.CanCancel)
        self.aoi = aoi
        self.start_date = start_date
        self.end_date = end_date
        self.cloud_cover_pct = cloud_cover_pct
        self.terrain_type = terrain_type
        self.thresholds = thresholds
        self.output_folder = output_folder
        self.progress_signal = progress_signal
        self.finished_signal = finished_signal
        self.mode = mode
        self.result_data = None
        self.error = None

    def run(self):
        from .gee_processor import run_classification, combine_masks

        try:
            def report(msg):
                self.progress_signal.emit(msg)

            if self.mode == 'export':
                report("Calculating vector export...")

            masks = run_classification(
                self.aoi, self.start_date, self.end_date,
                self.cloud_cover_pct, self.terrain_type,
                self.thresholds, report
            )

            if self.mode == 'preview':
                report("Generating preview tiles...")
                self.result_data = self._build_preview_tiles(masks)
                return True
            
            # ---------- Export mode (raster) ----------
            classified = combine_masks(masks)

            pixel_count = classified.connectedPixelCount(50, True)
            classified_cleaned = classified.updateMask(pixel_count.gte(9))

            timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            export_filename = f"lulc_classification_{timestamp}"

            report("Requesting direct download from Earth Engine...")
            download_url = classified_cleaned.getDownloadURL({
                'name': export_filename,
                'scale': 10,
                'region': self.aoi,
                'format': 'GEO_TIFF',
                'crs': 'EPSG:4326'
            })

            report("Downloading classification raster...")
            tif_path = os.path.join(self.output_folder, f"{export_filename}.tif")
            urllib.request.urlretrieve(download_url, tif_path)

            report("Loading raster into QGIS...")
            self.result_data = tif_path
            return True

        except Exception as e:
            self.error = str(e)
            return False

    def _build_preview_tiles(self, masks):
        composite_vis = {'bands': ['B4', 'B3', 'B2'], 'min': 0, 'max': 0.3}
        snow_vis = {'min': 0, 'max': 1, 'palette': ['white', '#E5EDF5']}
        water_vis = {'min': 0, 'max': 1, 'palette': ['white', '#4A90E2']}
        veg_vis = {'min': 0, 'max': 1, 'palette': ['white', "#266841"]}
        builtup_vis = {'min': 0, 'max': 1, 'palette': ['white', '#D9534F']}
        baresoil_vis = {'min': 0, 'max': 1, 'palette': ['white', "#F9D388"]}

        return {
            'composite': masks['composite'].getMapId(composite_vis)['tile_fetcher'].url_format,
            'snow': masks['snow_mask'].updateMask(masks['snow_mask']).getMapId(snow_vis)['tile_fetcher'].url_format,
            'water': masks['water_mask'].updateMask(masks['water_mask']).getMapId(water_vis)['tile_fetcher'].url_format,
            'vegetation': masks['vegetation_mask'].updateMask(masks['vegetation_mask']).getMapId(veg_vis)['tile_fetcher'].url_format,
            'builtup': masks['builtup_mask'].updateMask(masks['builtup_mask']).getMapId(builtup_vis)['tile_fetcher'].url_format,
            'baresoil': masks['baresoil_mask'].updateMask(masks['baresoil_mask']).getMapId(baresoil_vis)['tile_fetcher'].url_format,
        }

    def finished(self, result):
        self.finished_signal.emit(result, self.error, self.result_data)