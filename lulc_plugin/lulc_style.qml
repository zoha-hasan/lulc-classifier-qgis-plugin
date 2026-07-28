 <!DOCTYPE qgis PUBLIC 'http://mrcc.com/qgis.dtd' 'SYSTEM'>
<qgis version="3.34" styleCategories="Symbology">
  <pipe-data-defined-properties>
    <Option type="Map">
      <Option type="QString" name="name" value=""/>
      <Option name="properties"/>
      <Option type="QString" name="type" value="collection"/>
    </Option>
  </pipe-data-defined-properties>
  <rasterrenderer opacity="1" band="1" type="paletted" alphaBand="-1" nodataColor="">
    <rasterTransparency/>
    <minMaxOrigin>
      <limits>None</limits>
      <extent>WholeRaster</extent>
      <statAccuracy>Estimated</statAccuracy>
      <cumulativeCutLower>0.02</cumulativeCutLower>
      <cumulativeCutUpper>0.98</cumulativeCutUpper>
      <stdDevFactor>2</stdDevFactor>
    </minMaxOrigin>
    <colorPalette>
      <paletteEntry value="1" color="#4A90E2" alpha="255" label="Water"/>
      <paletteEntry value="2" color="#266841" alpha="255" label="Vegetation"/>
      <paletteEntry value="3" color="#D9534F" alpha="255" label="Built-up"/>
      <paletteEntry value="4" color="#F9D388" alpha="255" label="Bare Soil"/>
      <paletteEntry value="5" color="#E5EDF5" alpha="255" label="Snow"/>
    </colorPalette>
  </rasterrenderer>
  <blendMode>0</blendMode>
</qgis>