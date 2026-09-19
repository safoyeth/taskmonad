# TaskMonad

<p align="center">
  <b>A Monadic Pipeline and Asynchronous Task Execution Framework for Python</b>
  <br>
  <i>Clean functional composition &bull; Short-circuiting error isolation &bull; Built-in Qt desktop signals &bull; Declarative YAML pipelines</i>
</p>

<p align="center">
  <a href="#key-features">Features</a> &bull;
  <a href="#quick-start">Quick Start</a> &bull;
  <a href="#core-concepts">Core Concepts</a> &bull;
  <a href="#gui-integration-with-pyqt">Qt Integration</a> &bull;
  <a href="#declarative-yaml-workflows">YAML Pipelines</a> &bull;
  <a href="docs/en/architecture.md">Docs</a> &bull;
  <a href="README.ru.md"><b>Русская версия (Russian)</b></a>
</p>

---

## Overview

**TaskMonad** is a Python library that applies mathematical monadic abstractions to real-world asynchronous tasks. It bridges the gap between pure functional programming (`Task[T]`, `bind`, `map`, `tap`) and practical developer needs: `asyncio` concurrency, immutable state management, fail-fast error handling, fine-grained cron-like scheduling, and non-blocking desktop GUI execution (PyQt6/PyQt5/PySide6).

```python
pipeline = (
    Task("HourlyReportPipeline")
    .when(lambda do: do.hourly())
    .success(notify_success)
    .error(notify_error)
    >> Task.parallel(*download_tasks)
    >> read_all_files
    >> save_report
    << cleanup_files(temp_files)    # Operator <<: side-effect tap preserving report path
    >> dispatch_report
)

ctx, result = await pipeline.run()
```

---

## Key Features

- **Monadic Composition (`>>`)**: Chain synchronous functions, async coroutines, and `Task` instances seamlessly. Automatic lifting of return values into the monad.
- **Side-Effect Tap (`<<`)**: Execute logging, auditing, or cleanup steps without mutating or replacing the upstream value flowing to downstream nodes.
- **Short-Circuit Error Isolation**: Errors raise no unhandled exceptions into your loop; failed steps immediately short-circuit subsequent computations and gracefully route to error handlers.
- **Strict Monad Laws**: Fully compliant with mathematical **Left Identity**, **Right Identity**, and **Associativity** laws (verified by automated tests).
- **State Immutability (`TaskContext`)**: Deeply isolated dictionary storage prevents race conditions between parallel branches, while keeping non-serializable UI callbacks in metadata.
- **Fail-Fast Parallelism (`Task.parallel`)**: Concurrently run independent tasks via `asyncio.gather`, merging context updates into a unified state container.
- **Desktop UI Bridge (`TaskRunnerThread`)**: Dedicated background thread managing its own event loop and dispatching real-time Qt signals (`started`, `step_executed`, `log`, `finished`, `failed`).
- **Declarative YAML Execution**: Define complex multi-step pipelines in human-readable YAML/JSON with `@action` registration.

---

## Installation

```bash
# Clone and install in editable mode
git clone https://github.com/Safoyeth/taskmonad.git
cd taskmonad
pip install -e .
```

To include PyQt6 desktop support:
```bash
pip install PyQt6
```

---

## Quick Start

```python
import asyncio
from taskmonad import Task, TaskContext

async def calculate_discount(price: float) -> float:
    await asyncio.sleep(0.05)
    return price * 0.9

pipeline = (
    Task.of(100.0, name="InitialPrice")
    >> calculate_discount                    # Async coroutine step: 90.0
    << (lambda p: print(f"[LOG] Price: {p}")) # Tap side-effect
    >> (lambda p: f"Final: ${p:.2f}")        # Plain function: "Final: $90.00"
)

async def main():
    ctx, result = await pipeline.run()
    print("Result:", result)  # "Final: $90.00"

if __name__ == "__main__":
    asyncio.run(main())
```

---

## Core Concepts

### 1. Sequential Pipeline (`>>`)
The `>>` operator binds tasks together. If any step fails, subsequent steps are skipped:
```python
task = Task.of(10) >> (lambda x: x + 5) >> (lambda x: x * 2)
# Result: 30
```

### 2. Side-Effect Tap (`<<`)
Run a function or task as a side-effect, preserving the original upstream value for subsequent steps:
```python
task = (
    Task.of("data.csv")
    << (lambda file: print(f"Processing {file}..."))  # Preserves "data.csv"
    >> parse_csv                                     # Receives "data.csv"
)
```

### 3. Conditional Branching (`if_else`)
Execute conditional logic purely without nested `if` statements:
```python
task = Task.of(42).if_else(
    predicate=lambda x: x > 10,
    then_branch=Task.of("High"),
    else_branch=Task.of("Low"),
)
```

### 4. Parallel Concurrency (`Task.parallel`)
Execute multiple tasks concurrently and aggregate their outputs:
```python
task = Task.parallel(
    fetch_user_profile(user_id),
    fetch_user_orders(user_id),
    fetch_user_notifications(user_id),
)
# Returns [profile, orders, notifications]
```

### 5. Scheduling Triggers (`Schedule`)
Fluent API to specify execution frequencies:
```python
# Fluent bridge
task = Task("Poller").every.seconds(10)
task = Task("DailySync").every.day

# Full schedule builder
task = Task("Complex").when(
    lambda s: s.weekly().on("monday", "wednesday").at("09:00")
)
```

---

## GUI Integration with PyQt

Run asynchronous workflows in background threads without blocking desktop interfaces:

```python
from PyQt6.QtWidgets import QApplication, QMainWindow, QPushButton, QTextEdit, QVBoxLayout, QWidget
from PyQt6.QtCore import pyqtSlot
from taskmonad import Task
from taskmonad.qt_bridge import TaskRunnerThread

class App(QMainWindow):
    def __init__(self):
        super().__init__()
        self.btn = QPushButton("Run Pipeline")
        self.log = QTextEdit()
        
        layout = QVBoxLayout()
        layout.addWidget(self.btn)
        layout.addWidget(self.log)
        
        container = QWidget()
        container.setLayout(layout)
        self.setCentralWidget(container)
        
        self.btn.clicked.connect(self.run_task)
        self.runner = None

    def run_task(self):
        self.runner = TaskRunnerThread(my_pipeline)
        self.runner.signals.step_executed.connect(
            lambda step, status: self.log.append(f"[{status.upper()}] {step}")
        )
        self.runner.signals.finished.connect(
            lambda ctx: self.log.append("✅ Finished successfully!")
        )
        self.runner.signals.failed.connect(
            lambda err: self.log.append(f"❌ Error: {err}")
        )
        self.runner.start()
```

---

## Declarative YAML Workflows

Define workflows in clean YAML manifests:

```yaml
name: "ReportWorkflow"
schedule:
  mode: "interval"
  every: 30
  unit: "minutes"
pipeline:
  - type: "step"
    name: "FetchData"
    action: "download_sources"
  - type: "tap"
    name: "AuditLog"
    action: "log_event"
  - type: "step"
    name: "Aggregate"
    action: "merge_reports"
hooks:
  on_success: "notify_success"
  on_error: "notify_error"
```

Load and run with one line:
```python
from taskmonad import Task

pipeline = Task.from_yaml("workflow.yaml")
ctx, result = await pipeline.run()
```

---

## Running Tests

The test suite thoroughly verifies monadic laws, async concurrency, Qt bridging, short-circuit error propagation, and YAML deserialization:

```bash
pytest -v
```

---

## Documentation

Explore detailed topic guides in `docs/`:

- [Architecture & Monad Laws](docs/en/architecture.md)
- [Pipeline Composition Guide](docs/en/pipeline_guide.md)
- [API Reference](docs/en/api_reference.md)
- [Qt Desktop Integration](docs/en/qt_integration.md)
- [Declarative YAML Workflows](docs/en/declarative_yaml.md)

---

## License

MIT License. Designed with functional precision.
