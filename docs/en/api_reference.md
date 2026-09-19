# TaskMonad API Reference

Complete specification of all classes, methods, and functions in `taskmonad`.

---

## Module `taskmonad.task`

### `Task[T]`
A monadic container representing an asynchronous computation yielding a value of type `T` or an `Exception`.

#### Constructors
- **`Task(name: str = "Task", computation: Optional[Computation[T]] = None)`**  
  Constructs a task with a given name and computation coroutine. If `computation` is `None`, defaults to a unit returning `(ctx, None)`.
- **`Task.of(value: T, name: str = "Unit") -> Task[T]`** *(classmethod)*  
  Lifts a plain value or a coroutine into a `Task`.

#### Monadic Operations
- **`bind(fn: Callable[[T], Union[Task[U], U]], step_name: Optional[str] = None) -> Task[U]`**  
  Chains another computation $f$. If $f$ returns a raw value or coroutine, it is automatically lifted into a `Task`. Emits `"running"` and `"success"`/`"failure"` step signals.
- **`map(fn: Callable[[T], U]) -> Task[U]`**  
  Functor mapping. Transforms the value inside the task without unwrapping it manually.
- **`tap(effect: Union[Task[Any], Callable[..., Any]], step_name: Optional[str] = None) -> Task[T]`**  
  Runs a side-effect (callable taking 0 arguments, taking the current value, or returning a `Task`), returning the original incoming value unchanged. Short-circuits if the effect fails.

#### Operators
- **`task >> target`**  
  Shorthand for `task.bind(target)` or task sequencing if `target` is a `Task`.
- **`task << effect`**  
  Shorthand for `task.tap(effect)`.

#### Control Flow & Parallelism
- **`if_else(predicate, then_branch, else_branch) -> Task[U]`**  
  Branches execution conditionally. `predicate` can be a sync or async function returning a boolean.
- **`Task.parallel(*tasks_or_factories, name: Optional[str] = None) -> Task[List[Any]]`** *(classmethod)*  
  Executes tasks concurrently via `asyncio.gather`. Returns list of results and merges context data. Fail-fast upon any error.

#### Scheduling & Hooks
- **`when(config_fn: Union[Schedule, Callable[[Schedule], Schedule]]) -> Task[T]`**  
  Attaches schedule configuration to the task.
- **`every -> SchedulePropertyBridge[T]`**  
  Property returning a fluent bridge for configuring interval schedules.
- **`success(hook: Callable[[T, TaskContext], Any]) -> Task[T]`**  
  Registers a callback invoked upon successful completion.
- **`error(hook: Callable[[Exception, TaskContext], Any]) -> Task[T]`**  
  Registers a callback invoked upon failure.

#### Execution & Serialization
- **`async run(initial_ctx: Optional[TaskContext] = None) -> Tuple[TaskContext, Union[T, Exception]]`**  
  Executes the task coroutine asynchronously.
- **`Task.from_yaml(source: Union[str, Path]) -> Task[Any]`** *(classmethod)*  
  Loads a task pipeline from a YAML string or file path.
- **`Task.from_dict(data: dict[str, Any]) -> Task[Any]`** *(classmethod)*  
  Loads a task pipeline from a Python dictionary.

---

## Module `taskmonad.context`

### `TaskContext`
Immutable state container passed throughout the pipeline.

#### Attributes
- **`data: dict[str, Any]`**: Domain data dictionary. Deep-copied on modification.
- **`meta: dict[str, Any]`**: System metadata dictionary (signals, loggers). Shallow-copied.

#### Methods
- **`set(key: str, value: Any) -> TaskContext`**: Returns a new context with `data[key] = value`.
- **`update(new_data: dict[str, Any]) -> TaskContext`**: Returns a new context merging `new_data` into `data`.
- **`get(key: str, default: Any = None) -> Any`**: Fetches value from `data`.
- **`set_meta(key: str, value: Any) -> TaskContext`**: Returns a new context with `meta[key] = value`.
- **`get_meta(key: str, default: Any = None) -> Any`**: Fetches value from `meta`.

---

## Module `taskmonad.schedule`

### `Schedule`
Fluent builder for time triggers and periodic intervals.

#### Methods
- **`every(value: Union[int, float] = 1) -> Schedule`**
- **`milliseconds(value: Optional[Union[int, float]] = None) -> Schedule`**
- **`seconds(value: Optional[Union[int, float]] = None) -> Schedule`**
- **`minutes(value: Optional[Union[int, float]] = None) -> Schedule`**
- **`hours(value: Optional[Union[int, float]] = None) -> Schedule`**
- **`days(value: Optional[Union[int, float]] = None) -> Schedule`**
- **`secondly()`, `minutely()`, `hourly()`, `daily()`, `weekly()`, `monthly()`**
- **`once(date_str: Optional[str] = None, at_time: Optional[str] = None) -> Schedule`**
- **`delay(value: Union[int, float], unit: str = "seconds") -> Schedule`**
- **`on_startup() -> Schedule`**
- **`at(time_str: str) -> Schedule`**: Specifies time of day (`"14:30"`).
- **`on(*days: str) -> Schedule`**: Specifies days of week (`"monday"`, `"friday"`).
- **`on_days_of_month(*days: int) -> Schedule`**: Specifies dates (`1, 15`).
- **`cron(expression: str) -> Schedule`**: Cron expression string (`"*/5 * * * *"`).
- **`to_dict() -> Dict[str, Any]`** / **`from_dict(data: Dict[str, Any]) -> Schedule`**

---

## Module `taskmonad.qt_bridge`

### `TaskWorkerSignals(QObject)`
PyQt/PySide signals exposed by the background runner:
- **`started = pyqtSignal(str)`**: Task name when execution begins.
- **`step_executed = pyqtSignal(str, str)`**: Step name and status (`"running"`, `"success"`, `"failure"`).
- **`log = pyqtSignal(str)`**: Log messages emitted via `ctx.get_meta("emit_log")`.
- **`finished = pyqtSignal(object)`**: Emits the final `TaskContext`.
- **`failed = pyqtSignal(str)`**: Emits error message string upon failure.

### `TaskRunnerThread(QThread)`
Dedicated thread managing an asynchronous event loop for pipeline execution.

#### Constructor
- **`TaskRunnerThread(task: Task, initial_context: Optional[TaskContext] = None, parent=None)`**

---

## Module `taskmonad.serialization`

### `ActionRegistry`
Static registry of callable step handlers for YAML/JSON pipelines.

#### Methods
- **`@action(name: str)`** or **`ActionRegistry.register(name: str)`**: Decorator registering an action.
- **`ActionRegistry.get(name: str) -> Callable[..., Any]`**: Retrieves registered action.
- **`ActionRegistry.all() -> Dict[str, Callable[..., Any]]`**: Returns dictionary of all actions.
- **`ActionRegistry.clear()`**: Clears the registry.

### Utility Functions
- **`build_task_from_dict(data: Dict[str, Any]) -> Task[Any]`**
- **`build_task_from_yaml(source: Union[str, Path]) -> Task[Any]`**
