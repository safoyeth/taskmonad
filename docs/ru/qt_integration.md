# Руководство по интеграции с Qt

Библиотека `taskmonad` содержит встроенный модуль взаимодействия с графическими интерфейсами на **PyQt6**, **PyQt5** или **PySide6**. Он позволяет выполнять асинхронные конвейеры задач в отдельном потоке, плавно и безопасно обновляя виджеты GUI через сигналы Qt.

---

## 1. Установка

Для работы интеграции установите предпочтительный биндинг Qt:

```bash
# PyQt6 (рекомендуется)
pip install PyQt6

# Либо PyQt5
pip install PyQt5

# Либо PySide6
pip install PySide6
```

---

## 2. Архитектура: `TaskRunnerThread`

Выполнение асинхронного кода `asyncio` внутри настольного GUI без изоляции приводит к зависанию интерфейса или состоянию гонки потоков. Класс `taskmonad.qt_bridge.TaskRunnerThread` полностью решает эту задачу:

```
+-------------------------------------------------------------+
|                     Главный поток GUI                       |
|                                                             |
|   [ Кнопка запуска ] ──────► Создает TaskRunnerThread       |
|          ▲                                                  |
|          │ Сигналы Qt: step_executed, log, finished, failed  |
|          ▼                                                  |
|   [ Статус выполнения и QTextEdit логи ]                    |
+-------------------------------------------------------------+
                                │
                         Граница потоков
                                │
+-------------------------------------------------------------+
|              TaskRunnerThread (Фоновый QThread)             |
|                                                             |
|   1. Создает изолированный asyncio.new_event_loop()         |
|   2. Внедряет emit_step / emit_log в ctx.meta               |
|   3. Выполняет await pipeline.run(ctx)                      |
|   4. Генерирует сигналы Qt на каждом шаге                   |
+-------------------------------------------------------------+
```

---

## 3. Сигналы исполнителя

Объект `TaskRunnerThread.signals` предоставляет пять сигналов PyQt/PySide:

| Сигнал | Аргументы | Описание |
| :--- | :--- | :--- |
| `started` | `(str task_name)` | Генерируется в момент запуска выполнения пайплайна |
| `step_executed` | `(str step_name, str status)` | Генерируется до (`"running"`) и после (`"success"` или `"failure"`) выполнения шага |
| `log` | `(str message)` | Генерируется при вызове `ctx.get_meta("emit_log")("сообщение")` |
| `finished` | `(object context)` | Генерируется при успешном завершении с финальным `TaskContext` |
| `failed` | `(str error_message)` | Генерируется при сбое с текстом возникшего исключения |

---

## 4. Полный пример приложения

Рабочий пример приложения на PyQt6 с отображением прогресса и логов:

```python
import sys
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QPushButton, 
    QVBoxLayout, QTextEdit, QLabel, QWidget
)
from PyQt6.QtCore import pyqtSlot
from taskmonad import Task, TaskContext
from taskmonad.qt_bridge import TaskRunnerThread

# 1. Определение шагов пайплайна
def fetch_data():
    return Task.of("Данные с сервера", name="FetchData")

def process_data(data: str):
    return Task.of(data.upper(), name="ProcessData")

pipeline = (
    Task("DataSyncPipeline")
    >> fetch_data()
    >> process_data
)

# 2. Окно интерфейса Qt
class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("TaskMonad Qt Runner")
        self.resize(500, 350)

        self.btn_run = QPushButton("Запустить пайплайн")
        self.lbl_status = QLabel("Статус: Ожидание")
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

        # Создание и запуск фонового потока
        self.runner_thread = TaskRunnerThread(pipeline)
        self.runner_thread.signals.started.connect(self.on_started)
        self.runner_thread.signals.step_executed.connect(self.on_step)
        self.runner_thread.signals.finished.connect(self.on_finished)
        self.runner_thread.signals.failed.connect(self.on_failed)
        self.runner_thread.start()

    @pyqtSlot(str)
    def on_started(self, task_name: str):
        self.lbl_status.setText(f"Запущено: {task_name}")

    @pyqtSlot(str, str)
    def on_step(self, step_name: str, status: str):
        self.lbl_status.setText(f"Шаг: {step_name} [{status}]")
        self.log_area.append(f"[{status.upper()}] Узел: {step_name}")

    @pyqtSlot(object)
    def on_finished(self, ctx: TaskContext):
        self.lbl_status.setText("Статус: Завершено успешно!")
        self.log_area.append("\nПайплайн завершен без ошибок.")
        self.btn_run.setEnabled(True)

    @pyqtSlot(str)
    def on_failed(self, error: str):
        self.lbl_status.setText("Статус: Ошибка")
        self.log_area.append(f"\nОшибка пайплайна: {error}")
        self.btn_run.setEnabled(True)

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())
```

---

## 5. Отправка пользовательских логов из шагов

Внутри любого вычисления задачи можно отправлять текстовые логи напрямую в GUI через `ctx.get_meta("emit_log")`:

```python
async def custom_step(ctx: TaskContext):
    emit_log = ctx.get_meta("emit_log")
    if emit_log:
        emit_log("Подключение к удаленной базе данных...")
    
    # Выполнение работы
    if emit_log:
        emit_log("Подключение успешно установлено!")

    return ctx, "Connected"
```
