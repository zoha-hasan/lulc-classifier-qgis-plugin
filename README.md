# LULC Classifier

A QGIS plugin that performs Land Use / Land Cover (LULC) classification for any study area using Sentinel-2 satellite imagery, processed through Google Earth Engine (GEE). It detects five classes **water, vegetation, built-up, bare soil, and snow** and exports the result as a shapefile directly into QGIS.

---

# What this plugin does

1. You provide a study area (a shapefile boundary), a date range, and a maximum cloud cover percentage.
2. The plugin builds a cloud-masked Sentinel-2 composite over your area for that date range, on Google Earth Engine's servers.
3. It calculates a series of spectral indices (MNDWI, NDVI, NDRE, NDBI, BSI, NDSI) and applies threshold-based logic to classify every pixel into one of five classes.
4. You get a **live preview** of each class as a layer in QGIS, so you can visually check the result before committing to anything.
5. If you're happy with it, click **Export** the plugin combines all five masks into one classification, converts it to vector polygons, sends it to your Google Drive, downloads it back to your computer, and loads it into QGIS as a shapefile with both a numeric class code and a class name.
6. If you're not happy with it, click **Edit Inputs** to adjust your area, date range, or thresholds and try again, no need to close and reopen the plugin.

---

# What to expect from the results

This plugin is a **threshold-based classifier**, not a machine-learning model, it applies a fixed set of rules (spectral index thresholds) to Sentinel-2 imagery. This has limitations worth knowing before you rely on the output:

- **Spatial resolution:** Sentinel-2's core bands are 10m resolution. Small or narrow features like thin streams, individual buildings, small paths may not be fully or accurately captured. A single pixel covers a 10 by 10m area, so anything smaller gets blended into whatever else shares that pixel.
- **Cloud gaps:** Pixels that are cloud-covered on every available image within your chosen date range will have no data at all, and will appear as small gaps in the output. This isn't fixable by the classification logic itself. Widening your date range gives the compositor more images to pull a clear pixel from, which usually reduces these gaps.
- **Threshold accuracy:** The default thresholds for each terrain profile (Plain/Hilly and High Elevation) are tuned to give a reasonable approximation of real-world land cover, but they are starting points, not guarantees. Every landscape has different lighting, terrain, and characteristics, so results will vary in accuracy from one study area to another.
- **Built-up vs. bare soil** is the hardest class boundary to get right, these two land types can have overlapping spectral signatures at 10m resolution, especially in mixed rural or informal-settlement areas. Expect this boundary to need some manual threshold tuning if the default isn't accurate for the selected study area, although some inaccuracies are to be expected due to the spatial resolution.
- **Recommended workflow:** After running a preview, compare it visually against the Sentinel-2 composite layer (which is added automatically) or against Google Satellite basemap imagery from roughly the same time period. If something looks clearly wrong, adjust the relevant threshold and re-run. Expect to get *close* to an accurate classification with some tuning but obtaining a zero-error result may not be realistic for an index-based classifier at this resolution.

---

## Requirements

- QGIS 3.x
- A free Google Earth Engine account
- A Google Cloud project with the Earth Engine API and Google Drive API enabled
- A Google Drive account (for temporary export storage)

You do **not** need to know how to code to use this plugin, the one-time setup below just involves creating some free Google accounts/credentials and pasting a few values into a settings window.

---

## One-time setup

### 1. Create a Google Earth Engine account
Go to [signup.earthengine.google.com](https://signup.earthengine.google.com) and sign up (free, for noncommercial/research use).

### 2. Create a Google Cloud service account
1. Go to [console.cloud.google.com](https://console.cloud.google.com).
2. Create a new project (or use an existing one).
3. Search for and enable the **Earth Engine API**.
4. Search for and enable the **Google Drive API**.
5. Go to *IAM & Admin then Service Accounts* then create a new service account.
6. Create a **JSON key** for that service account and download it. Keep this file private, treat it like a password.

### 3. Create a Google Drive folder for exports
1. In your own Google Drive, create a new folder (e.g. `GEE_LULC_exports`).
2. Right-click the folder then **Share** then add your service account's email address (found in the JSON key file, looks like `xxxx@yyyy.iam.gserviceaccount.com`) with **Editor** access.
3. Note the folder's name and make sure it's unique within your Drive, since the plugin finds it by name.

### 4. Enter your credentials into the plugin
1. Install and enable the plugin in QGIS (steps below).
2. Open the plugin and click **Settings** button in the plugin window.
3. Enter:
   - Your service account email
   - The path to your JSON key file
   - Your Google Drive folder name
4. Click **Save**. This only needs to be done once, QGIS remembers it for future sessions.

---

## Installing the plugin

1. Download or clone this repository.
2. Copy the plugin folder into your QGIS plugins directory:
   - **Windows:** `%APPDATA%\QGIS\QGIS3\profiles\default\python\plugins\`
   - **macOS:** `~/Library/Application Support/QGIS/QGIS3/profiles/default/python/plugins/`
   - **Linux:** `~/.local/share/QGIS/QGIS3/profiles/default/python/plugins/`
3. Open QGIS then *Plugins go to Manage and Install Plugins and Installed* then check the box next to **LULC Classifier** to enable it.
4. A new toolbar icon and a *Plugins -> LULC Classifier* menu entry will appear.

### Python package requirements
This plugin needs two Python packages installed into QGIS's own Python environment (not your system Python):

```
"C:\Program Files\QGIS 3.44.1\apps\Python312\python.exe" -m pip install earthengine-api google-api-python-client google-auth
```
(Adjust the path to match your actual QGIS installation and version. Run this on your system command prompt.)

---

## How to use it

1. Click the **LULC Classifier** toolbar icon or menu entry and a dockable panel opens.
2. **Inputs page:**
   - Select your study area shapefile (must be in WGS84 / EPSG:4326).
   - Select an output folder (where the final shapefile will be saved locally).
   - Set a start and end date for the Sentinel-2 composite.
   - Set a maximum cloud cover percentage.
   - Click **Next**.
3. **Thresholds page:**
   - Choose a terrain type i.e *Plain / Slightly Hilly* or *High Elevation* which loads a matching set of default thresholds.
   - Leave **"Use default values"** checked to use the tuned defaults, or uncheck it to edit any threshold manually (each has an operator `>`, `<`, or `=`, and a value).
   - Click **Run**.
4. The plugin processes in the background, a progress label shows each stage as it happens (building composite, calculating each mask, etc.). QGIS remains fully usable while this runs.
5. Once done, six layers appear on the map: the Sentinel-2 composite and one layer per class (snow, water, vegetation, built-up, bare soil). Pan and zoom freely to inspect them.
6. Choose:
   - **Export:** reprocesses and exports the final combined classification as a shapefile (via Google Drive), then loads it into QGIS automatically.
   - **Edit Inputs:** returns to the input/threshold pages with your previous values preserved, so you can adjust and re-run.

---

## Output

The final exported shapefile contains polygon features with two attributes:
- `class:` a numeric code (1 = Water, 2 = Vegetation, 3 = Built-up, 4 = Bare Soil, 5 = Snow)
- `class_name:` the same classes as text

---

## Known limitations

- Requires each user to set up their own free Google Earth Engine and Google Cloud credentials, this cannot be bundled into the plugin itself for security and quota reasons.
- Free-tier Earth Engine accounts have a compute quota; heavy repeated use (many preview runs in a short time) can temporarily slow down processing.
- Built-up and bare soil classification accuracy varies significantly by region and may require manual threshold tuning per study area.
- Cloud-covered pixels with no clear observation in the date range will appear as small gaps in the output.
- Vegetation is classified as a single class; distinguishing agriculture from natural vegetation was evaluated but found unreliable without multi-date (temporal) imagery, so it was not included.

---

## License

This project is licensed under the MIT License, see the LINCENSE file for details.

---