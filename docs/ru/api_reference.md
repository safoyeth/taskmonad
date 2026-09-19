# Справочник API TaskMonad

Полная спецификация всех классов, методов и функций библиотеки `taskmonad`.

---

## Модуль `taskmonad.task`

### `Task[T]`
Монадический контейнер, инкапсулирующий асинхронное вычисление, возвращающее значение типа `T` или объект `Exception`.

#### Конструкторы
- **`Task(name: str = "Task", computation: Optional[Computation[T]] = None)`**  
  Создает задачу с указанным именем и функцией вычисления. Если `computation` не передан, создается единичный узел, возвращающий `(ctx, None)`.
- **`Task.of(value: T, name: str = "Unit") -> Task[T]`** *(classmethod)*  
  Поднимает (lift) обычное значение или корутину в контекст монады `Task`.

#### Монадические операции
- **`bind(fn: Callable[[T], Union[Task[U], U]], step_name: Optional[str] = None) -> Task[U]`**  
  Связывает текущую задачу со следующей функцией $f$. Если $f$ возвращает не `Task`, а обычное значение или корутину, оно автоматически оборачивается в `Task`. Автоматически генерирует сигналы шагов `"running"` и `"success"`/`"failure"`.
- **`map(fn: Callable[[T], U]) -> Task[U]`**  
  Функторное преобразование. Изменяет внутреннее значение без необходимости ручного извлечения.
- **`tap(effect: Union[Task[Any], Callable[..., Any]], step_name: Optional[str] = None) -> Task[T]`**  
  Выполняет побочный эффект (функцию без аргументов, функцию от текущего значения или вложенный `Task`), возвращая исходное входное значение без изменений. При ошибке побочного эффекта пайплайн прерывается.

#### Операторы
- **`task >> target`**  
  Сокращенный синтаксис для `task.bind(target)` (или последовательное выполнение, если `target` является объектом `Task`).
- **`task << effect`**  
  Сокращенный синтаксис для `task.tap(effect)`.

#### Управление потоком и параллелизм
- **`if_else(predicate, then_branch, else_branch) -> Task[U]`**  
  Условное ветвление. `predicate` может быть синхронной или асинхронной функцией, возвращающей `bool`.
- **`Task.parallel(*tasks_or_factories, name: Optional[str] = None) -> Task[List[Any]]`** *(classmethod)*  
  Конкурентное выполнение задач через `asyncio.gather`. Возвращает список результатов и объединяет данные контекстов. При возникновении ошибки срабатывает fail-fast прерывание.

#### Расписание и хуки
- **`when(config_fn: Union[Schedule, Callable[[Schedule], Schedule]]) -> Task[T]`**  
  Привязывает конфигурацию расписания к задаче.
- **`every -> SchedulePropertyBridge[T]`**  
  Свойство, возвращающее текучий билдер (fluent bridge) для настройки интервальных запусков.
- **`success(hook: Callable[[T, TaskContext], Any]) -> Task[T]`**  
  Регистрирует коллбэк, вызываемый при успешном завершении задачи.
- **`error(hook: Callable[[Exception, TaskContext], Any]) -> Task[T]`**  
  Регистрирует коллбэк, вызываемый при ошибке выполнения.

#### Выполнение и десериализация
- **`async run(initial_ctx: Optional[TaskContext] = None) -> Tuple[TaskContext, Union[T, Exception]]`**  
  Асинхронно выполняет задачу и возвращает кортеж `(финальный_контекст, результат)`.
- **`Task.from_yaml(source: Union[str, Path]) -> Task[Any]`** *(classmethod)*  
  Создает пайплайн из строки YAML или пути к файлу.
- **`Task.from_dict(data: dict[str, Any]) -> Task[Any]`** *(classmethod)*  
  Создает пайплайн из словаря Python.

---

## Модуль `taskmonad.context`

### `TaskContext`
Иммутабельный контейнер состояния, передаваемый сквозь конвейер задач.

#### Поля
- **`data: dict[str, Any]`**: Словарь бизнес-данных. Глубоко копируется при любой модификации.
- **`meta: dict[str, Any]`**: Системные метаданные (сигналы, логгеры). Поверхностно копируются.

#### Методы
- **`set(key: str, value: Any) -> TaskContext`**: Возвращает новый контекст с установленным `data[key] = value`.
- **`update(new_data: dict[str, Any]) -> TaskContext`**: Возвращает новый контекст, объединяя `new_data` с `data`.
- **`get(key: str, default: Any = None) -> Any`**: Получает значение из `data`.
- **`set_meta(key: str, value: Any) -> TaskContext`**: Возвращает новый контекст с установленным `meta[key] = value`.
- **`get_meta(key: str, default: Any = None) -> Any`**: Получает значение из `meta`.

---

## Модуль `taskmonad.schedule`

### `Schedule`
Конструктор правил периодичности и триггеров запуска.

#### Методы
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
- **`at(time_str: str) -> Schedule`**: Фиксирует время суток (`"14:30"`).
- **`on(*days: str) -> Schedule`**: Дни недели (`"monday"`, `"friday"`).
- **`on_days_of_month(*days: int) -> Schedule`**: Числа месяца (`1, 15`).
- **`cron(expression: str) -> Schedule`**: Произвольное cron-выражение (`"*/5 * * * *"`).
- **`to_dict() -> Dict[str, Any]`** / **`from_dict(data: Dict[str, Any]) -> Schedule`**

---

## Модуль `taskmonad.qt_bridge`

### `TaskWorkerSignals(QObject)`
Сигналы PyQt/PySide для связывания с GUI:
- **`started = pyqtSignal(str)`**: Имя задачи в момент старта.
- **`step_executed = pyqtSignal(str, str)`**: Имя шага и статус (`"running"`, `"success"`, `"failure"`).
- **`log = pyqtSignal(str)`**: Сообщение лога из `ctx.get_meta("emit_log")`.
- **`finished = pyqtSignal(object)`**: Финальный `TaskContext` при успешном завершении.
- **`failed = pyqtSignal(str)`**: Текст ошибки при сбое.

### `TaskRunnerThread(QThread)`
Выделенный рабочий поток с собственным циклом событий `asyncio`.

#### Конструктор
- **`TaskRunnerThread(task: Task, initial_context: Optional[TaskContext] = None, parent=None)`**

---

## Модуль `taskmonad.serialization`

### `ActionRegistry`
Статический реестр обработчиков шагов для построения пайплайнов из декларативных манифестов.

#### Методы
- **`@action(name: str)`** или **`ActionRegistry.register(name: str)`**: Декоратор регистрации действия.
- **`ActionRegistry.get(name: str) -> Callable[..., Any]`**: Получение зарегистрированного действия.
- **`ActionRegistry.all() -> Dict[str, Callable[..., Any]]`**: Словарь всех зарегистрированных действий.
- **`ActionRegistry.clear()`**: Очистка реестра.

### Функции
- **`build_task_from_dict(data: Dict[str, Any]) -> Task[Any]`**
- **`build_task_from_yaml(source: Union[str, Path]) -> Task[Any]`**
