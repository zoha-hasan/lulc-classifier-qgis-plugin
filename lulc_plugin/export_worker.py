import time
import datetime
import os
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
                report("Calculating classification export...")

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

            report("Calculating export tiles...")
            bounds = self.aoi.bounds().getInfo()['coordinates'][0]
            lons = [pt[0] for pt in bounds]
            lats = [pt[1] for pt in bounds]
            xmin, xmax = min(lons), max(lons)
            ymin, ymax = min(lats), max(lats)

            area_m2 = self.aoi.area(1).getInfo()
            max_bytes = 50331648 * 0.85
            bytes_per_pixel = 2
            max_pixels_per_tile = max_bytes / bytes_per_pixel
            total_pixels_est = area_m2 / (10 * 10)
            num_tiles = max(1, int((total_pixels_est / max_pixels_per_tile) ** 0.5) + 1)

            report(f"Splitting into {num_tiles}x{num_tiles} tiles at full resolution...")

            x_step = (xmax - xmin) / num_tiles
            y_step = (ymax - ymin) / num_tiles

            tile_folder = os.path.join(self.output_folder, export_filename)
            os.makedirs(tile_folder, exist_ok=True)
            tile_paths = []

            tile_num = 0
            for i in range(num_tiles):
                for j in range(num_tiles):
                    tile_num += 1
                    report(f"Downloading tile {tile_num} of {num_tiles * num_tiles}...")

                    tile_geom = ee.Geometry.Rectangle([
                        xmin + i * x_step, ymin + j * y_step,
                        xmin + (i + 1) * x_step, ymin + (j + 1) * y_step
                    ])

                    tile_download_url = classified_cleaned.clip(tile_geom).getDownloadURL({
                        'name': f"tile_{i}_{j}",
                        'scale': 10,
                        'region': tile_geom,
                        'format': 'GEO_TIFF',
                        'crs': 'EPSG:4326'
                    })

                    tile_path = os.path.join(tile_folder, f"tile_{i}_{j}.tif")
                    urllib.request.urlretrieve(tile_download_url, tile_path)
                    tile_paths.append(tile_path)

            report("Merging tiles into final raster...")
            from osgeo import gdal
            merged_path = os.path.join(self.output_folder, f"{export_filename}.tif")
            gdal.Warp(merged_path, tile_paths)

            report("Loading raster into QGIS...")
            self.result_data = merged_path
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