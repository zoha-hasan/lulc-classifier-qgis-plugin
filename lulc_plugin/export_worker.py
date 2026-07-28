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

            # ---------- Export mode ----------
            classified = combine_masks(masks)

            # Filter out tiny fragments (likely cloud-gap noise) before vectorizing
            pixel_count = classified.connectedPixelCount(50, True)
            classified_cleaned = classified.updateMask(pixel_count.gte(4))

            report("Vectorizing classification...")
            vectors = classified_cleaned.reduceToVectors(
                geometry=self.aoi,
                scale=10,
                geometryType='polygon',
                labelProperty='class',
                maxPixels=1e13,
                bestEffort=True
            )

            class_names = ee.Dictionary({
                '1': 'Water',
                '2': 'Vegetation',
                '3': 'Built-up',
                '4': 'Bare Soil',
                '5': 'Snow',
            })

            def add_class_name(feature):
                class_num = feature.get('class')
                class_name = class_names.get(ee.Number(class_num).format('%d'))
                return feature.set('class_name', class_name)

            vectors = vectors.map(add_class_name)

            timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            export_filename = f"lulc_classification_{timestamp}"

            report("Requesting direct download from Earth Engine...")
            download_url = vectors.getDownloadURL(filetype='SHP', filename=export_filename)

            report("Downloading shapefile...")
            zip_path = os.path.join(self.output_folder, f"{export_filename}.zip")
            urllib.request.urlretrieve(download_url, zip_path)

            report("Extracting shapefile...")
            extract_folder = os.path.join(self.output_folder, export_filename)
            os.makedirs(extract_folder, exist_ok=True)
            with zipfile.ZipFile(zip_path, 'r') as zip_ref:
                zip_ref.extractall(extract_folder)

            os.remove(zip_path)

            shp_path = None
            for fname in os.listdir(extract_folder):
                if fname.endswith('.shp'):
                    shp_path = os.path.join(extract_folder, fname)
                    break

            if not shp_path:
                self.error = "Downloaded file did not contain a .shp file."
                return False

            report("Loading shapefile into QGIS...")
            self.result_data = shp_path
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