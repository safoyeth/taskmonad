from __future__ import annotations
import asyncio
from typing import Optional

# Поддержка PyQt6 с фолбэком на PyQt5 или PySide6
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
                "Для работы qt_bridge требуется установить PyQt6, PyQt5 или PySide6. "
                "Выполните: pip install PyQt6"
            )

from taskmonad.task import Task
from taskmonad.context import TaskContext


class TaskWorkerSignals(QObject):
    started = pyqtSignal(str)                   # task_name
    step_executed = pyqtSignal(str, str)        # step_name, status ("running" | "success" | "failure")
    log = pyqtSignal(str)                       # текстовое сообщение для лога
    finished = pyqtSignal(object)               # финальный TaskContext
    failed = pyqtSignal(str)                    # текст ошибки


class TaskRunnerThread(QThread):
    """
    Фоновый рабочий поток QThread с выделенным изолированным asyncio event loop.
    Позволяет выполнять монадический Task без зависания интерфейса PyQt.
    """
    def __init__(self, task: Task, initial_context: Optional[TaskContext] = None, parent=None):
        super().__init__(parent)
        self.task = task
        self.ctx = initial_context or TaskContext()
        self.signals = TaskWorkerSignals()

    def run(self):
        # Поднимаем чистый независимый цикл событий asyncio внутри отдельного потока
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

        # Пробрасываем отправку сигналов в meta-контекст, чтобы шаги задачи могли слать логи в GUI
        self.ctx = self.ctx.set_meta("emit_log", lambda msg: self.signals.log.emit(str(msg)))
        self.ctx = self.ctx.set_meta("emit_step", lambda name, status: self.signals.step_executed.emit(str(name), str(status)))

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