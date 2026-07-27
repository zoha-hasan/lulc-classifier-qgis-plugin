from qgis.PyQt.QtWidgets import (
    QDialog, QVBoxLayout, QLabel, QLineEdit, QPushButton, QHBoxLayout
)
from qgis.gui import QgsFileWidget
from qgis.core import QgsSettings


class SettingsDialog(QDialog):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("GEE / Drive Settings")
        self.setMinimumWidth(450)

        settings = QgsSettings()

        layout = QVBoxLayout()

        layout.addWidget(QLabel("Service account email (from Google Cloud Console):"))
        self.email_input = QLineEdit()
        self.email_input.setText(settings.value("lulc_plugin/service_account", ""))
        layout.addWidget(self.email_input)

        layout.addWidget(QLabel("JSON key file (from GEE service account, authorized for Drive export as well):"))
        self.key_widget = QgsFileWidget()
        self.key_widget.setStorageMode(QgsFileWidget.GetFile)
        self.key_widget.setFilter("JSON Files (*.json)")
        self.key_widget.setFilePath(settings.value("lulc_plugin/key_path", ""))
        layout.addWidget(self.key_widget)

        layout.addWidget(QLabel("Google Drive folder name (name should be unique and of an existing folder):"))
        self.folder_id_input = QLineEdit()
        self.folder_id_input.setText(settings.value("lulc_plugin/drive_folder_id", ""))
        layout.addWidget(self.folder_id_input)

        btn_layout = QHBoxLayout()
        self.save_btn = QPushButton("Save")
        self.save_btn.clicked.connect(self.save_settings)
        btn_layout.addWidget(self.save_btn)
        layout.addLayout(btn_layout)

        self.setLayout(layout)

    def save_settings(self):
        settings = QgsSettings()
        settings.setValue("lulc_plugin/service_account", self.email_input.text())
        settings.setValue("lulc_plugin/key_path", self.key_widget.filePath())
        settings.setValue("lulc_plugin/drive_folder_id", self.folder_id_input.text())
        self.accept()


def credentials_are_saved():
    """Quick check used by the main dialog before allowing Next."""
    settings = QgsSettings()
    email = settings.value("lulc_plugin/service_account", "")
    key_path = settings.value("lulc_plugin/key_path", "")
    folder_id = settings.value("lulc_plugin/drive_folder_id", "")
    return bool(email and key_path and folder_id)