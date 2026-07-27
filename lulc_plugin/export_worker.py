import time
import io
import ee
import datetime
from qgis.core import QgsTask, QgsProject, QgsVectorLayer
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload


class ClassificationTask(QgsTask):
    def __init__(self, aoi, start_date, end_date, cloud_cover_pct, terrain_type, thresholds, output_folder,
             key_path, drive_folder_id, progress_signal, finished_signal, mode='preview'):
        super().__init__("LULC Classification", QgsTask.CanCancel)
        self.aoi = aoi
        self.start_date = start_date
        self.end_date = end_date
        self.cloud_cover_pct = cloud_cover_pct
        self.terrain_type = terrain_type
        self.thresholds = thresholds
        self.output_folder = output_folder
        self.key_path = key_path
        self.drive_folder_id = drive_folder_id
        self.progress_signal = progress_signal
        self.finished_signal = finished_signal
        self.mode = mode
        self.result_data = None
        self.error = None
        self.export_filename = None

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

            report("Vectorizing classification...")
            vectors = classified.reduceToVectors(
                geometry=self.aoi,
                scale=10,
                geometryType='polygon',
                labelProperty='class',
                maxPixels=1e13
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
            self.export_filename = export_filename
            
            report("Starting export to Google Drive...")
            task = ee.batch.Export.table.toDrive(
                collection=vectors,
                description=export_filename,
                folder=self.drive_folder_id,
                fileNamePrefix=export_filename,
                fileFormat='SHP'
            )
            task.start()

            while task.active():
                report("Export running on Google Earth Engine servers...")
                time.sleep(10)

            status = task.status()
            if status['state'] != 'COMPLETED':
                self.error = f"Export failed: {status}"
                return False

            report("Export finished. Downloading from Drive...")
            downloaded_path = self._download_from_drive(report)

            report("Loading shapefile into QGIS...")
            self.result_data = downloaded_path
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

    def _download_from_drive(self, report):
        creds = service_account.Credentials.from_service_account_file(
            self.key_path,
            scopes=['https://www.googleapis.com/auth/drive.readonly']
        )
        drive_service = build('drive', 'v3', credentials=creds)

        # Find the exported files (shapefile = multiple parts: .shp .shx .dbf .prj)
        query = f"name contains '{self.export_filename}'"
        results = drive_service.files().list(q=query, fields="files(id, name)").execute()
        files = results.get('files', [])

        if not files:
            raise Exception("No exported files found in Drive folder.")

        local_shp_path = None
        for f in files:
            report(f"Downloading {f['name']}...")
            request = drive_service.files().get_media(fileId=f['id'])
            local_path = f"{self.output_folder}/{f['name']}"
            fh = io.FileIO(local_path, 'wb')
            downloader = MediaIoBaseDownload(fh, request)
            done = False
            while not done:
                status, done = downloader.next_chunk()
            if f['name'].endswith('.shp'):
                local_shp_path = local_path

        return local_shp_path

    def finished(self, result):
        self.finished_signal.emit(result, self.error, self.result_data)