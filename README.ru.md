# TaskMonad

<p align="center">
  <b>Монадический фреймворк для конструирования конвейеров задач и асинхронного выполнения в Python</b>
  <br>
  <i>Функциональная композиция &bull; Изоляция ошибок (short-circuiting) &bull; Интеграция с Qt GUI сигналами &bull; Декларативные YAML-пайплайны</i>
</p>

<p align="center">
  <a href="#ключевые-возможности">Возможности</a> &bull;
  <a href="#быстрый-старт">Быстрый старт</a> &bull;
  <a href="#базовые-концепции">Концепции</a> &bull;
  <a href="#интеграция-с-qt-gui">Интеграция с Qt</a> &bull;
  <a href="#декларативные-пайплайны-в-yaml">YAML Пайплайны</a> &bull;
  <a href="docs/ru/architecture.md">Документация</a> &bull;
  <a href="README.md"><b>English version</b></a>
</p>

---

## Обзор

**TaskMonad** — это Python-библиотека, переносящая математическую абстракцию монады на решение прикладных задач асинхронного программирования. Библиотека объединяет строгое функциональное программирование (`Task[T]`, `bind`, `map`, `tap`) и практические требования современной разработки: конкурентность `asyncio`, иммутабельное состояние, мгновенную локализацию ошибок без падения цикла событий, гибкое планирование запусков и неблокирующее выполнение задач в графических интерфейсах (PyQt6 / PyQt5 / PySide6).

```python
pipeline = (
    Task("HourlyReportPipeline")
    .when(lambda do: do.hourly())
    .success(notify_success)
    .error(notify_error)
    .always(cleanup_resources)      # <--- Гарантированный хук завершения (always / finally_)
    >> Task.parallel(*download_tasks)
    >> read_all_files
    >> save_report
    << cleanup_files(temp_files)    # Оператор <<: побочный эффект без изменения report_path
    >> dispatch_report
)

ctx, result = await pipeline.run()
```

---

## Ключевые возможности

- **Монадическая композиция (`>>`)**: Последовательное связывание синхронных функций, асинхронных корутин и экземпляров `Task`. Автоматическое поднятие (lift) возвращаемых значений в монаду.
- **Побочные эффекты без мутации (`<<`)**: Выполнение операций логирования, аудита, сохранения или очистки без модификации значения, передаваемого дальше по пайплайну.
- **Изоляция ошибок (Short-Circuiting)**: Никаких неперехваченных исключений, роняющих event loop. При возникновении ошибки последующие шаги автоматически пропускаются, а управление передается зарегистрированным хукам.
- **Соблюдение монадических законов**: Строгое выполнение законов **левой идентичности**, **правой идентичности** и **ассоциативности** (подтверждено набором юнит-тестов).
- **Иммутабельное состояние (`TaskContext`)**: Глубоко изолированное хранилище данных исключает состояние гонки между параллельными ветвями, сохраняя несериализуемые дескрипторы GUI в метаданных.
- **Параллелизм с защитой от сбоев (`Task.parallel`)**: Конкурентный запуск независимых подзадач через `asyncio.gather` с объединением контекстов и стратегией fail-fast.
- **Мост с настольным GUI (`TaskRunnerThread`)**: Отдельный поток `QThread` с собственным циклом событий `asyncio` и отправкой сигналов Qt в реальном времени (`started`, `step_executed`, `log`, `finished`, `failed`).
- **Декларативное описание в YAML**: Описание сложных многошаговых процессов в человекочитаемом формате YAML/JSON с реестром действий `@action`.

---

## Установка

```bash
# Клонирование и установка в режиме разработки
git clone https://github.com/Safoyeth/taskmonad.git
cd taskmonad
pip install -e .
```

Для работы с графическим интерфейсом PyQt6:
```bash
pip install PyQt6
```

---

## Быстрый старт

```python
import asyncio
from taskmonad import Task, TaskContext

async def calculate_discount(price: float) -> float:
    await asyncio.sleep(0.05)
    return price * 0.9

pipeline = (
    Task.of(100.0, name="InitialPrice")
    >> calculate_discount                    # Асинхронный шаг: 90.0
    << (lambda p: print(f"[ЛОГ] Цена: {p}")) # Побочный эффект (tap)
    >> (lambda p: f"Итог: ${p:.2f}")         # Синхронная функция: "Итог: $90.00"
)

async def main():
    ctx, result = await pipeline.run()
    print("Результат:", result)  # "Итог: $90.00"

if __name__ == "__main__":
    asyncio.run(main())
```

---

## Базовые концепции

### 1. Последовательный конвейер (`>>`)
Оператор `>>` связывает шаги. Если на каком-то этапе происходит ошибка, выполнение оставшихся узлов прекращается:
```python
task = Task.of(10) >> (lambda x: x + 5) >> (lambda x: x * 2)
# Результат: 30
```

### 2. Побочные эффекты через Tap (`<<`)
Запуск функции или задачи в виде побочного эффекта с сохранением исходного значения для последующих шагов:
```python
task = (
    Task.of("data.csv")
    << (lambda file: print(f"Обработка {file}..."))  # Сохраняет "data.csv"
    >> parse_csv                                    # Получает "data.csv"
)
```

### 3. Условное ветвление (`if_else`)
Чисто функциональное ветвление без вложенных конструкций `if`:
```python
task = Task.of(42).if_else(
    predicate=lambda x: x > 10,
    then_branch=Task.of("Высокое"),
    else_branch=Task.of("Низкое"),
)
```

### 4. Конкурентный параллелизм (`Task.parallel`)
Одновременный запуск нескольких подзадач со сбором результатов:
```python
task = Task.parallel(
    fetch_user_profile(user_id),
    fetch_user_orders(user_id),
    fetch_user_notifications(user_id),
)
# Возвращает список [profile, orders, notifications]
```

### 5. Расписания и триггеры (`Schedule`)
Гибкий API для настройки периодичности выполнения:
```python
# Текучий интерфейс (fluent bridge)
task = Task("Poller").every.seconds(10)
task = Task("DailySync").every.day

# Полный конструктор расписаний
task = Task("Complex").when(
    lambda s: s.weekly().on("monday", "wednesday").at("09:00")
)
```

### 6. Терминальные хуки жизненного цикла (`success`, `error`, `always` / `finally_`)
Регистрация функций обратного вызова при завершении конвейера:
- `.success(hook)`: Вызывается только при успешном завершении без ошибок.
- `.error(hook)`: Вызывается при возникновении ошибки или коротком замыкании (short-circuit).
- `.always(hook)` (алиас `.finally_(hook)`): **Выполняется ВСЕГДА**, вне зависимости от того, была ошибка или нет.

> [!IMPORTANT]
> **КЛЮЧЕВОЕ АРХИТЕКТУРНОЕ ПРАВИЛО: Сначала хуки, затем — монадическая композиция!**  
> В TaskMonad терминальные хуки и конфигурация расписания **должны объявляться на корневой задаче ДО связывания шагов через операторы `>>` и `<<`**.
>
> Каждый оператор монадического связывания (`>>`, `<<`, `map`) копирует зарегистрированные хуки дальше по цепочке пайплайна через внутренний механизм наследования (`_inherit`). Объявление хуков на корневом объекте гарантирует, что результирующий пайплайн сохранит их и гарантированно вызовет при завершении.

```python
# ✅ ПРАВИЛЬНЫЙ ПАТТЕРН: Сначала объявляются хуки!
pipeline = (
    Task("MyPipeline")
    .success(lambda res, ctx: print(f"Успех: {res}"))
    .error(lambda err, ctx: print(f"Сбой: {err}"))
    .always(lambda res_or_err, ctx: print("Гарантированная очистка ресурсов."))
    >> step_1
    >> step_2
    >> step_3
)
```

---

## Интеграция с Qt GUI

Запуск асинхронных задач в фоновом потоке без блокировки графического интерфейса пользователя:

```python
from PyQt6.QtWidgets import QApplication, QMainWindow, QPushButton, QTextEdit, QVBoxLayout, QWidget
from PyQt6.QtCore import pyqtSlot
from taskmonad import Task
from taskmonad.qt_bridge import TaskRunnerThread

class App(QMainWindow):
    def __init__(self):
        super().__init__()
        self.btn = QPushButton("Запустить конвейер")
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
            lambda ctx: self.log.append("✅ Успешно завершено!")
        )
        self.runner.signals.failed.connect(
            lambda err: self.log.append(f"❌ Ошибка: {err}")
        )
        self.runner.start()
```

---

## Декларативные пайплайны в YAML

Конфигурация конвейеров задач в файлах YAML:

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
  on_finally: "cleanup_resources"
```

Загрузка и запуск одной строкой:
```python
from taskmonad import Task

pipeline = Task.from_yaml("workflow.yaml")
ctx, result = await pipeline.run()
```

---

## Запуск тестов

Тестовый набор проверяет выполнение законов монады, конкурентность, интеграцию с Qt, изоляцию ошибок и парсинг YAML:

```bash
pytest -v
```

---

## Подробная документация

Изучите специализированные руководства в каталоге `docs/`:

- [Архитектура и законы монады](docs/ru/architecture.md)
- [Руководство по композиции пайплайнов](docs/ru/pipeline_guide.md)
- [Справочник API](docs/ru/api_reference.md)
- [Интеграция с Qt GUI](docs/ru/qt_integration.md)
- [Декларативные пайплайны в YAML](docs/ru/declarative_yaml.md)

---

## Лицензия

MIT License.
