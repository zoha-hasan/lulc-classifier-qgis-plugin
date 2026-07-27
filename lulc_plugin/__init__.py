def classFactory(iface):
    from .lulc_plugin import LulcPlugin
    return LulcPlugin(iface)