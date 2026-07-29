from qgis.PyQt.QtWidgets import QWidget, QHBoxLayout, QLabel, QComboBox, QLineEdit


class ThresholdRow(QWidget):
    def __init__(self, label_text, default_operator, default_value):
        super().__init__()
        self.default_operator = default_operator
        self.default_value = default_value

        layout = QHBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)

        layout.addWidget(QLabel(label_text))

        self.operator_box = QComboBox()
        self.operator_box.addItems([">", "<", "="])
        self.operator_box.setCurrentText(default_operator)
        layout.addWidget(self.operator_box)

        self.value_input = QLineEdit(str(default_value))
        layout.addWidget(self.value_input)

        self.setLayout(layout)

    def set_editable(self, editable, force_default=False):
        self.operator_box.setEnabled(editable)
        self.value_input.setEnabled(editable)
        if force_default:
            self.operator_box.setCurrentText(self.default_operator)
            self.value_input.setText(str(self.default_value))

    def get_operator(self):
        return self.operator_box.currentText()

    def get_value(self):
        try:
            return float(self.value_input.text())
        except ValueError:
            return self.default_value