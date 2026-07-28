import ee


def build_operator_expr(image, operator, value):
    """Turns ('>', 0.35) into image.gt(0.35), etc."""
    if operator == ">":
        return image.gt(value)
    elif operator == "<":
        return image.lt(value)
    else:
        return image.eq(value)


def mask_s2_clouds(image):
    qa = image.select('QA60')
    cloud_bit = 1 << 10
    cirrus_bit = 1 << 11
    mask = qa.bitwiseAnd(cloud_bit).eq(0).And(qa.bitwiseAnd(cirrus_bit).eq(0))
    return image.updateMask(mask).divide(10000)

def strip_z(coords):
    """Recursively remove the Z coordinate from nested coordinate lists."""
    if isinstance(coords[0], (int, float)):
        return coords[:2]
    return [strip_z(c) for c in coords]


def shapefile_to_ee_geometry(shp_path):
    from qgis.core import QgsVectorLayer, QgsProject, QgsCoordinateTransform, QgsCoordinateReferenceSystem
    import json

    layer = QgsVectorLayer(shp_path, "aoi", "ogr")
    if not layer.isValid():
        raise ValueError("Could not load shapefile.")

    target_crs = QgsCoordinateReferenceSystem("EPSG:4326")
    transform = QgsCoordinateTransform(layer.crs(), target_crs, QgsProject.instance())

    feature = next(layer.getFeatures())
    geom = feature.geometry()
    geom.transform(transform)

    geojson_dict = json.loads(geom.asJson())
    geojson_dict['coordinates'] = strip_z(geojson_dict['coordinates'])

    return ee.Geometry(geojson_dict)

def run_classification(aoi, start_date, end_date, cloud_cover_pct, terrain_type, thresholds, progress_callback):
    """
    terrain_type: 'plain' or 'high_elevation' - controls processing order
    cloud_cover_pct: user-entered number, e.g. 20, replaces the old hardcoded value
    """

    progress_callback("Building Sentinel-2 composite...")

    collection = (
        ee.ImageCollection('COPERNICUS/S2_SR_HARMONIZED')
        .filterBounds(aoi)
        .filterDate(start_date, end_date)
        .filter(ee.Filter.lt('CLOUDY_PIXEL_PERCENTAGE', cloud_cover_pct))
        .map(mask_s2_clouds)
    )
    composite = collection.median().clip(aoi)

    # ---------- Snow ----------
    progress_callback("Calculating snow mask (NDSI)...")
    ndsi = composite.normalizedDifference(['B3', 'B11']).rename('NDSI')
    nir = composite.select('B8')
    op, val = thresholds['ndsi']
    ndsi_cond = build_operator_expr(ndsi, op, val)
    op, val = thresholds['nir_floor_snow']
    nir_cond = build_operator_expr(nir, op, val)
    snow_mask = ndsi_cond.And(nir_cond)
    non_snow_composite = composite.updateMask(snow_mask.Not())

    # ---------- Water ----------
    progress_callback("Calculating water mask (MNDWI)...")
    mndwi = non_snow_composite.normalizedDifference(['B3', 'B11']).rename('MNDWI')
    op, val = thresholds['mndwi']
    water_mask = build_operator_expr(mndwi, op, val)

    pixel_count = water_mask.connectedPixelCount(100, True)
    water_mask_clean = water_mask.updateMask(pixel_count.gte(12))

    ndvi = non_snow_composite.normalizedDifference(['B8', 'B4']).rename('NDVI')
    op, val = thresholds['water_ndvi']
    ndvi_check = build_operator_expr(ndvi, op, val)
    water_mask_verified = water_mask_clean.And(ndvi_check)

    non_water_composite = non_snow_composite.updateMask(water_mask_verified.Not())

    def compute_ndbi_bsi(img):
        ndbi = img.normalizedDifference(['B11', 'B8']).rename('NDBI')
        bsi = img.expression(
            '((SWIR1 + RED) - (NIR + BLUE)) / ((SWIR1 + RED) + (NIR + BLUE))',
            {
                'SWIR1': img.select('B11'),
                'RED': img.select('B4'),
                'NIR': img.select('B8'),
                'BLUE': img.select('B2')
            }
        ).rename('BSI')
        return ndbi, bsi

    def compute_veg(img):
        ndvi_v = img.normalizedDifference(['B8', 'B4']).rename('NDVI')
        ndre_v = img.normalizedDifference(['B8', 'B5']).rename('NDRE')
        op, val = thresholds['veg_ndvi']
        ndvi_cond = build_operator_expr(ndvi_v, op, val)
        op, val = thresholds['veg_ndre']
        ndre_cond = build_operator_expr(ndre_v, op, val)
        return ndvi_cond.And(ndre_cond)

    def compute_builtup(img):
        ndbi, bsi = compute_ndbi_bsi(img)
        op, val = thresholds['builtup_ndbi']
        ndbi_cond = build_operator_expr(ndbi, op, val)
        op, val = thresholds['builtup_bsi']
        bsi_cond = build_operator_expr(bsi, op, val)
        return ndbi_cond.And(bsi_cond)

    # ---------- Order differs by terrain type ----------
    if terrain_type == 'high_elevation':
        progress_callback("Calculating built-up mask (NDBI + BSI)...")
        builtup_mask = compute_builtup(non_water_composite)
        after_builtup_composite = non_water_composite.updateMask(builtup_mask.Not())

        progress_callback("Calculating vegetation mask (NDVI + NDRE)...")
        vegetation_mask = compute_veg(after_builtup_composite)
        remaining_composite = after_builtup_composite.updateMask(vegetation_mask.Not())

    else:  # 'plain'
        progress_callback("Calculating vegetation mask (NDVI + NDRE)...")
        vegetation_mask = compute_veg(non_water_composite)
        after_veg_composite = non_water_composite.updateMask(vegetation_mask.Not())

        progress_callback("Calculating built-up mask (NDBI + BSI)...")
        builtup_mask = compute_builtup(after_veg_composite)
        remaining_composite = after_veg_composite.updateMask(builtup_mask.Not())

    # ---------- Bare soil ----------
    progress_callback("Calculating bare soil mask...")
    ndbi2, bsi2 = compute_ndbi_bsi(remaining_composite)
    op, val = thresholds['baresoil_ndbi']
    ndbi2_cond = build_operator_expr(ndbi2, op, val)
    op, val = thresholds['baresoil_bsi_low']
    bsi2_low = build_operator_expr(bsi2, op, val)
    op, val = thresholds['baresoil_bsi_high']
    bsi2_high = build_operator_expr(bsi2, op, val)

    baresoil_mask_strict = ndbi2_cond.And(bsi2_low).And(bsi2_high)
    baresoil_mask = baresoil_mask_strict.Or(baresoil_mask_strict.Not())

    return {
        'composite': composite,
        'snow_mask': snow_mask,
        'water_mask': water_mask_verified,
        'vegetation_mask': vegetation_mask,
        'builtup_mask': builtup_mask,
        'baresoil_mask': baresoil_mask,
    }


def combine_masks(masks):
    classified = ee.Image(0) \
        .where(masks['water_mask'], 1) \
        .where(masks['vegetation_mask'], 2) \
        .where(masks['builtup_mask'], 3) \
        .where(masks['baresoil_mask'], 4) \
        .where(masks['snow_mask'], 5) \
        .rename('class')
    classified = classified.updateMask(classified.neq(0))
    return classified