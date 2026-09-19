# Декларативные пайплайны в YAML

`taskmonad` позволяет декларативно описывать и настраивать асинхронные конвейеры задач в формате YAML или JSON. Это разделяет бизнес-логику шагов и общую оркестрацию пайплайна.

---

## 1. Регистрация действий (Action Registry)

Чтобы функции Python были доступны загрузчику YAML, зарегистрируйте их с помощью декоратора `@action`:

```python
from taskmonad import action, Task

@action("fetch_urls")
def fetch_urls():
    return ["https://api.one.org", "https://api.two.org"]

@action("download_url")
def download_url(url: str):
    return f"Данные из {url}"

@action("audit_log")
def audit_log(data):
    print(f"[АУДИТ] Обработка данных: {data}")

@action("send_notification")
def send_notification(summary: str):
    print(f"[УВЕДОМЛЕНИЕ] Успешно завершено: {summary}")
```

---

## 2. Спецификация манифеста YAML

Манифест задачи поддерживает метаданные, расписание, последовательность шагов и финальные хуки:

```yaml
name: "DataIngestionPipeline"

# 1. Расписание и триггеры
schedule:
  mode: "interval"
  every: 15
  unit: "minutes"

# 2. Последовательность конвейера
pipeline:
  # Обычный шаг связывания (bind)
  - type: "step"
    name: "FetchSourceUrls"
    action: "fetch_urls"

  # Шаг побочного эффекта (tap: логирование без изменения передаваемых данных)
  - type: "tap"
    name: "AuditStage"
    action: "audit_log"

  # Параллельное выполнение
  - type: "parallel"
    name: "ParallelDownload"
    branches:
      - action: "download_url"
        params:
          url: "https://api.one.org"
      - action: "download_url"
        params:
          url: "https://api.two.org"

  # Финальная агрегация
  - type: "step"
    name: "FormatReport"
    action: "format_report"

# 3. Финальные хуки
hooks:
  on_success: "send_notification"
  on_error: "alert_admin"
```

---

## 3. Типы шагов конвейера

### 3.1 `type: "step"`
Стандартный монадический шаг связывания (`bind`). Результат работы предыдущего шага передается на вход действию.
```yaml
- type: "step"
  name: "Transform"
  action: "transform_data"
  params:
    multiplier: 10
```

### 3.2 `type: "tap"`
Шаг побочного эффекта (`<<` / `tap`). Выполняет действие, но сохраняет предыдущее значение для передачи последующим узлам.
```yaml
- type: "tap"
  name: "DiskSync"
  action: "save_backup"
```

### 3.3 `type: "parallel"`
Параллельно запускает несколько действий через `Task.parallel`. Результаты агрегируются в список.
```yaml
- type: "parallel"
  name: "FetchAll"
  branches:
    - action: "fetch_source_a"
    - action: "fetch_source_b"
```

### 3.4 `type: "if_else"`
Условное ветвление на основе зарегистрированного действия-предиката.
```yaml
- type: "if_else"
  condition: "is_admin_user"
  then: "handle_admin_flow"
  else: "handle_standard_flow"
```

---

## 4. Загрузка и исполнение

Загрузка и запуск производятся методом `Task.from_yaml()`:

```python
import asyncio
from pathlib import Path
from taskmonad import Task

async def main():
    # Загрузка напрямую из файла или строки
    pipeline = Task.from_yaml("pipeline.yaml")
    
    # Запуск конвейера
    ctx, result = await pipeline.run()
    print("Результат:", result)

if __name__ == "__main__":
    asyncio.run(main())
```
