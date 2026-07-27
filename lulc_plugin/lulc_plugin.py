from qgis.PyQt.QtWidgets import QAction
from qgis.PyQt.QtCore import Qt
from .main_dialog import MainDockWidget


class LulcPlugin:
    def __init__(self, iface):
        self.iface = iface
        self.action = None
        self.dock_widget = None

    def initGui(self):
        self.action = QAction("LULC Classifier", self.iface.mainWindow())
        self.action.triggered.connect(self.run)
        self.iface.addToolBarIcon(self.action)
        self.iface.addPluginToMenu("LULC Classifier", self.action)

    def unload(self):
        self.iface.removeToolBarIcon(self.action)
        self.iface.removePluginMenu("LULC Classifier", self.action)
        if self.dock_widget:
            self.iface.removeDockWidget(self.dock_widget)

    def run(self):
        if self.dock_widget is None:
            self.dock_widget = MainDockWidget(self.iface)
            self.iface.addDockWidget(Qt.RightDockWidgetArea, self.dock_widget)
        else:
            self.dock_widget.show()