# Руководство по композиции пайплайнов

В этом руководстве описывается процесс создания, компоновки и оркестрации конвейеров задач с помощью `taskmonad`.

---

## 1. Создание атомарных задач

Создавать задачи можно двумя основными способами:

### 1.1 `Task.of(value)`
Создает задачу, оборачивающую готовое значение или корутину:
```python
from taskmonad import Task

# Оборачивание синхронного значения
task = Task.of(42, name="InitialNumber")

# Оборачивание корутины
async def fetch_token():
    return "secret-token-xyz"

token_task = Task.of(fetch_token(), name="FetchToken")
```

### 1.2 Пользовательское вычисление: `Task(name, computation)`
Используется, когда шагу нужен прямой доступ к контексту `TaskContext`:
```python
from taskmonad import Task, TaskContext

async def calculate_hash(ctx: TaskContext):
    user_id = ctx.get("user_id")
    computed_hash = f"HASH_{user_id}"
    
    # Возвращаем (обновленный_контекст, значение_результата)
    return ctx.set("user_hash", computed_hash), computed_hash

task = Task(name="ComputeHash", computation=calculate_hash)
```

---

## 2. Последовательная композиция: оператор `>>`

Оператор `>>` связывает шаги в конвейер. Библиотека автоматически поднимает (lift) разные типы функций в монаду:

### 2.1 Обычная синхронная функция
```python
pipeline = (
    Task.of(10)
    >> (lambda x: x + 5)       # Обычная функция: 15
    >> (lambda x: x * 2)       # Обычная функция: 30
    >> (lambda x: f"Res: {x}") # Обычная функция: "Res: 30"
)
```

### 2.2 Асинхронная корутинная функция
```python
import asyncio

async def fetch_user_data(user_id: int) -> dict:
    await asyncio.sleep(0.1)
    return {"id": user_id, "name": "Alice"}

pipeline = Task.of(1) >> fetch_user_data
```

### 2.3 Функция, возвращающая объект `Task`
```python
def process_order(item_id: str) -> Task[str]:
    async def comp(ctx: TaskContext):
        return ctx, f"ORDER_FOR_{item_id}"
    return Task(name=f"Order({item_id})", computation=comp)

pipeline = Task.of("item-123") >> process_order
```

### 2.4 Прямое связывание двух объектов `Task`
Если справа от оператора находится готовый экземпляр `Task`, предыдущее возвращенное значение игнорируется, а состояние контекста сохраняется:
```python
step1 = Task.of("первый")
step2 = Task.of("второй")

pipeline = step1 >> step2  # Результат: "второй"
```

---

## 3. Побочные эффекты: оператор `<<` (Tap)

Оператор `<<` выполняет побочный эффект (логирование, запись на диск, аудит, удаление временных файлов) **без изменения значения, передаваемого по цепочке**.

```python
def cleanup_temp_files(filepaths: list[str]):
    # Удаляет временные файлы
    for f in filepaths:
        Path(f).unlink(missing_ok=True)

pipeline = (
    Task.of("data_report.csv")
    << (lambda path: print(f"Обработка отчета: {path}..."))
    >> generate_report
    << cleanup_temp_files                                 # Очищает файлы
    >> send_email_notification                            # Получает отчет из generate_report!
)
```

> [!NOTE]
> Если побочный эффект в `<<` сгенерирует исключение, пайплайн прервется по правилу короткого замыкания (short-circuit).

---

## 4. Условное ветвление: `if_else`

Метод `Task.if_else` обеспечивает чисто функциональное ветвление на основе синхронных или асинхронных предикатов.

```python
def route_payment(amount: float):
    return (
        Task.of(amount).if_else(
            predicate=lambda val: val > 10_000,
            then_branch=lambda val: Task.of(f"Отправлено на ручной контроль: ${val}"),
            else_branch=lambda val: Task.of(f"Проведено автоматически: ${val}"),
        )
    )
```

Асинхронные предикаты поддерживаются из коробки:
```python
async def check_inventory(product_id: str) -> bool:
    await asyncio.sleep(0.05)
    return True

pipeline = (
    Task.of("PROD-999")
    .if_else(
        predicate=check_inventory,
        then_branch=Task.of("В наличии"),
        else_branch=Task.of("Нет на складе"),
    )
)
```

---

## 5. Параллелизм: `Task.parallel`

`Task.parallel` запускает несколько независимых задач конкурентно через `asyncio.gather`.

```python
import asyncio
from taskmonad import Task, TaskContext

def download_source(url: str):
    async def comp(ctx: TaskContext):
        await asyncio.sleep(0.2)
        return ctx.set(f"downloaded_{url}", True), f"Данные из {url}"
    return Task(name=f"Download({url})", computation=comp)

pipeline = (
    Task.parallel(
        download_source("https://api.one.com"),
        download_source("https://api.two.com"),
        download_source("https://api.three.com"),
    )
    >> (lambda results: "\n---\n".join(results))
)

ctx, report = await pipeline.run()
```

- Результаты собираются в список в исходном порядке перечисления задач.
- Если хотя бы одна ветка падает с ошибкой, параллельный шаг завершается немедленно с этой ошибкой (fail-fast).

---

## 6. Настройка расписания

К любой задаче можно прикрепить конфигурацию периодичности или триггеров:

### Текучий интерфейс (Fluent Bridge)
```python
# Запуск каждые 5 секунд
task = Task("Worker").every.seconds(5)

# Запуск каждые 200 миллисекунд
task = Task("FastPoller").every.milliseconds(200)

# Запуск каждый день
task = Task("DailyJob").every.day
```

### Объект `Schedule`
```python
from taskmonad import Schedule

task = Task("ComplexSchedule").when(
    lambda s: s.weekly().on("monday", "friday").at("08:30")
)
```

---

## 7. Финальные хуки: `success` и `error`

Хуки вызываются автоматически при завершении метода `.run()`:

```python
pipeline = (
    Task("ProductionPipeline")
    .success(lambda result, ctx: print(f"Успех! Результат: {result}"))
    .error(lambda err, ctx: print(f"Сбой: {err}"))
    >> validate_input
    >> execute_pipeline
)

await pipeline.run()
```
