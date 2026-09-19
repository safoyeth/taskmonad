from pathlib import Path
import sys

# Allow direct execution without installing package
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QPushButton, 
    QVBoxLayout, QTextEdit, QLabel, QWidget
)
from PyQt6.QtCore import pyqtSlot
from taskmonad import Task
from taskmonad.qt_bridge import TaskRunnerThread
from examples.pipeline_demo import pipeline

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("TaskMonad Manager")
        self.resize(550, 450)

        self.btn_run = QPushButton("Запустить конвейер задач")
        self.lbl_status = QLabel("Статус: Готов к запуску")
        self.log_area = QTextEdit()
        self.log_area.setReadOnly(True)

        layout = QVBoxLayout()
        layout.addWidget(self.btn_run)
        layout.addWidget(self.lbl_status)
        layout.addWidget(self.log_area)

        container = QWidget()
        container.setLayout(layout)
        self.setCentralWidget(container)

        self.btn_run.clicked.connect(self.start_task)
        self.runner_thread = None

    def start_task(self):
        self.btn_run.setEnabled(False)
        self.log_area.clear()
        self.log_area.append("Запуск пайплайна...")

        self.runner_thread = TaskRunnerThread(pipeline)
        self.runner_thread.signals.step_executed.connect(self.on_step)
        self.runner_thread.signals.finished.connect(self.on_finished)
        self.runner_thread.signals.failed.connect(self.on_failed)
        self.runner_thread.start()

    @pyqtSlot(str, str)
    def on_step(self, step_name: str, status: str):
        self.lbl_status.setText(f"Шаг: {step_name} -> {status.upper()}")
        self.log_area.append(f"[{status.upper()}] Выполняется узел: {step_name}")

    @pyqtSlot(object)
    def on_finished(self, ctx):
        self.lbl_status.setText("Статус: Завершено успешно")
        self.log_area.append("\n✅ Задача завершена без ошибок!")
        self.log_area.append(f"Итоговые данные: {ctx.data}")
        self.btn_run.setEnabled(True)

    @pyqtSlot(str)
    def on_failed(self, error: str):
        self.lbl_status.setText("Статус: Ошибка")
        self.log_area.append(f"\n❌ Ошибка: {error}")
        self.btn_run.setEnabled(True)

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())