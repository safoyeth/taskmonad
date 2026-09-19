# Qt Desktop Integration Guide

`taskmonad` includes built-in bridge support for desktop applications built with **PyQt6**, **PyQt5**, or **PySide6**. It allows running async pipelines in a background thread while updating GUI widgets smoothly via Qt signals.

---

## 1. Installation

To enable Qt support, install your preferred Qt binding:

```bash
# PyQt6 (recommended)
pip install PyQt6

# Or PyQt5
pip install PyQt5

# Or PySide6
pip install PySide6
```

---

## 2. The Architecture: `TaskRunnerThread`

Running `asyncio` inside a desktop UI can easily freeze the interface or lead to cross-thread race conditions. `taskmonad.qt_bridge.TaskRunnerThread` provides a clean separation:

```
+-------------------------------------------------------------+
|                      Main GUI Thread                        |
|                                                             |
|   [ Start Button ] ───────► Creates TaskRunnerThread       |
|          ▲                                                  |
|          │ Qt Signals: step_executed, log, finished, failed  |
|          ▼                                                  |
|   [ Status Label & QTextEdit Logs ]                         |
+-------------------------------------------------------------+
                                │
                         Thread boundary
                                │
+-------------------------------------------------------------+
|              TaskRunnerThread (Background QThread)          |
|                                                             |
|   1. Instantiates private asyncio.new_event_loop()          |
|   2. Injects emit_step / emit_log into ctx.meta             |
|   3. Awaits pipeline.run(ctx)                               |
|   4. Dispatches Qt signals to UI at each step               |
+-------------------------------------------------------------+
```

---

## 3. Worker Signals

`TaskRunnerThread.signals` exposes five PyQt/PySide signals:

| Signal | Arguments | Description |
| :--- | :--- | :--- |
| `started` | `(str task_name)` | Emitted when the runner starts executing the task |
| `step_executed` | `(str step_name, str status)` | Emitted before (`"running"`) and after (`"success"` or `"failure"`) each step |
| `log` | `(str message)` | Emitted whenever `ctx.get_meta("emit_log")("message")` is called |
| `finished` | `(object context)` | Emitted on pipeline success with the final `TaskContext` |
| `failed` | `(str error_message)` | Emitted if an unhandled exception halts the pipeline |

---

## 4. Complete Application Example

Below is a complete working example demonstrating a PyQt6 application with real-time step monitoring:

```python
import sys
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QPushButton, 
    QVBoxLayout, QTextEdit, QLabel, QWidget
)
from PyQt6.QtCore import pyqtSlot
from taskmonad import Task, TaskContext
from taskmonad.qt_bridge import TaskRunnerThread

# 1. Define sample tasks
def fetch_data():
    return Task.of("Payload from server", name="FetchData")

def process_data(data: str):
    return Task.of(data.upper(), name="ProcessData")

pipeline = (
    Task("DataSyncPipeline")
    >> fetch_data()
    >> process_data
)

# 2. Build the Qt Window
class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("TaskMonad Qt Runner")
        self.resize(500, 350)

        self.btn_run = QPushButton("Run Pipeline")
        self.lbl_status = QLabel("Status: Idle")
        self.log_area = QTextEdit()
        self.log_area.setReadOnly(True)

        layout = QVBoxLayout()
        layout.addWidget(self.btn_run)
        layout.addWidget(self.lbl_status)
        layout.addWidget(self.log_area)

        container = QWidget()
        container.setLayout(layout)
        self.setCentralWidget(container)

        self.btn_run.clicked.connect(self.start_pipeline)
        self.runner_thread = None

    def start_pipeline(self):
        self.btn_run.setEnabled(False)
        self.log_area.clear()

        # Instantiate background runner
        self.runner_thread = TaskRunnerThread(pipeline)
        self.runner_thread.signals.started.connect(self.on_started)
        self.runner_thread.signals.step_executed.connect(self.on_step)
        self.runner_thread.signals.finished.connect(self.on_finished)
        self.runner_thread.signals.failed.connect(self.on_failed)
        self.runner_thread.start()

    @pyqtSlot(str)
    def on_started(self, task_name: str):
        self.lbl_status.setText(f"Started: {task_name}")

    @pyqtSlot(str, str)
    def on_step(self, step_name: str, status: str):
        self.lbl_status.setText(f"Step: {step_name} [{status}]")
        self.log_area.append(f"[{status.upper()}] Node: {step_name}")

    @pyqtSlot(object)
    def on_finished(self, ctx: TaskContext):
        self.lbl_status.setText("Status: Completed successfully!")
        self.log_area.append("\nPipeline finished without errors.")
        self.btn_run.setEnabled(True)

    @pyqtSlot(str)
    def on_failed(self, error: str):
        self.lbl_status.setText("Status: Error")
        self.log_area.append(f"\nPipeline Error: {error}")
        self.btn_run.setEnabled(True)

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())
```

---

## 5. Emitting Custom Logs from Steps

Inside any task computation, you can emit logs directly to the Qt UI using `ctx.get_meta("emit_log")`:

```python
async def custom_step(ctx: TaskContext):
    emit_log = ctx.get_meta("emit_log")
    if emit_log:
        emit_log("Connecting to remote database...")
    
    # Do work
    if emit_log:
        emit_log("Database connected successfully!")

    return ctx, "Connected"
```
