# Declarative YAML Pipelines

`taskmonad` enables you to define and configure asynchronous workflows declaratively in YAML or JSON. This separates business logic from pipeline orchestration.

---

## 1. Action Registration

To make Python functions accessible to the YAML loader, register them using the `@action` decorator:

```python
from taskmonad import action, Task

@action("fetch_urls")
def fetch_urls():
    return ["https://api.one.org", "https://api.two.org"]

@action("download_url")
def download_url(url: str):
    return f"Data from {url}"

@action("audit_log")
def audit_log(data):
    print(f"[AUDIT] Processing: {data}")

@action("send_notification")
def send_notification(summary: str):
    print(f"[NOTIFICATION] Done: {summary}")
```

---

## 2. YAML Manifest Specification

A YAML pipeline definition supports metadata, scheduling, steps, and hooks:

```yaml
name: "DataIngestionPipeline"

# 1. Schedule Configuration
schedule:
  mode: "interval"
  every: 15
  unit: "minutes"

# 2. Pipeline Sequence
pipeline:
  # Standard step (binds incoming value)
  - type: "step"
    name: "FetchSourceUrls"
    action: "fetch_urls"

  # Tap step (side-effect: incoming data passed to audit_log, but untouched for next step)
  - type: "tap"
    name: "AuditStage"
    action: "audit_log"

  # Parallel execution step
  - type: "parallel"
    name: "ParallelDownload"
    branches:
      - action: "download_url"
        params:
          url: "https://api.one.org"
      - action: "download_url"
        params:
          url: "https://api.two.org"

  # Final aggregation step
  - type: "step"
    name: "FormatReport"
    action: "format_report"

# 3. Terminal Hooks
hooks:
  on_success: "send_notification"
  on_error: "alert_admin"
```

---

## 3. Step Types

### 3.1 `type: "step"`
Represents a standard monadic binding step. The return value of the previous step is passed as the input to this action.
```yaml
- type: "step"
  name: "Transform"
  action: "transform_data"
  params:
    multiplier: 10
```

### 3.2 `type: "tap"`
Represents a monadic tap (`<<`). Runs the action as a side-effect, but preserves the upstream value flowing to subsequent steps.
```yaml
- type: "tap"
  name: "DiskSync"
  action: "save_backup"
```

### 3.3 `type: "parallel"`
Executes multiple registered actions concurrently. Returns aggregated results as a list.
```yaml
- type: "parallel"
  name: "FetchAll"
  branches:
    - action: "fetch_source_a"
    - action: "fetch_source_b"
```

### 3.4 `type: "if_else"`
Executes conditional branching based on a registered boolean condition action.
```yaml
- type: "if_else"
  condition: "is_admin_user"
  then: "handle_admin_flow"
  else: "handle_standard_flow"
```

---

## 4. Loading and Executing

Load and run pipelines with `Task.from_yaml()`:

```python
import asyncio
from pathlib import Path
from taskmonad import Task

async def main():
    # Load directly from string or file path
    pipeline = Task.from_yaml("pipeline.yaml")
    
    # Run the pipeline
    ctx, result = await pipeline.run()
    print("Result:", result)

if __name__ == "__main__":
    asyncio.run(main())
```
