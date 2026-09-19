from __future__ import annotations
import asyncio
from typing import Optional

try:
    from PyQt6.QtCore import QObject, QThread, pyqtSignal
except ImportError:
    try:
        from PyQt5.QtCore import QObject, QThread, pyqtSignal
    except ImportError:
        try:
            
            # pyrefly: ignore [missing-import]
            from PySide6.QtCore import QObject, QThread, Signal as pyqtSignal
        except ImportError:
            raise ImportError(
                "Для qt_bridge требуется PyQt6, PyQt5 или PySide6. Установите: pip install PyQt6"
            )

from taskmonad.task import Task
from taskmonad.context import TaskContext


class TaskWorkerSignals(QObject):
    started = pyqtSignal(str)                   # task_name
    step_executed = pyqtSignal(str, str)        # step_name, status ("running" | "success" | "failure")
    log = pyqtSignal(str)                       # log message
    finished = pyqtSignal(object)               # final TaskContext
    failed = pyqtSignal(str)                    # error message


class TaskRunnerThread(QThread):
    def __init__(self, task: Task, initial_context: Optional[TaskContext] = None, parent=None):
        super().__init__(parent)
        self.task = task
        self.ctx = initial_context or TaskContext()
        self.signals = TaskWorkerSignals()

    def run(self):
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

        self.ctx = self.ctx.set_meta("emit_log", lambda msg: self.signals.log.emit(str(msg)))
        self.ctx = self.ctx.set_meta(
            "emit_step", lambda name, status: self.signals.step_executed.emit(str(name), str(status))
        )

        self.signals.started.emit(self.task.name)

        try:
            final_ctx, result = loop.run_until_complete(self.task.run(self.ctx))
            if isinstance(result, Exception):
                self.signals.failed.emit(str(result))
            else:
                self.signals.finished.emit(final_ctx)
        except Exception as e:
            self.signals.failed.emit(str(e))
        finally:
            loop.close()