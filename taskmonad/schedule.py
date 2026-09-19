from __future__ import annotations
from typing import Any, Dict, List, Optional, Union


class Schedule:
    """Универсальная конфигурация триггеров и расписаний любой гранулярности."""

    def __init__(self):
        # Режимы: "interval", "once", "delay", "daily", "weekly", "monthly", "cron", "on_startup"
        self.mode: str = "interval"
        
        # Единицы: "milliseconds", "seconds", "minutes", "hours", "days", "weeks"
        self.interval_unit: Optional[str] = None
        self.interval_value: Union[int, float] = 1

        self.at_time: Optional[str] = None          # "14:30" или "14:30:00"
        self.date: Optional[str] = None             # "2026-10-15"
        self.weekdays: List[str] = []               # ["monday", "tuesday"]
        self.month_days: List[int] = []             # [1, 15]
        self.cron_expr: Optional[str] = None        # "*/5 * * * *"

    # =========================================================================
    # 1. Интервальные запуски (от миллисекунд до недель)
    # =========================================================================

    def every(self, value: Union[int, float] = 1) -> Schedule:
        self.mode = "interval"
        self.interval_value = value
        return self

    def milliseconds(self, value: Optional[Union[int, float]] = None) -> Schedule:
        self.mode = "interval"
        self.interval_unit = "milliseconds"
        if value is not None:
            self.interval_value = value
        return self

    def seconds(self, value: Optional[Union[int, float]] = None) -> Schedule:
        self.mode = "interval"
        self.interval_unit = "seconds"
        if value is not None:
            self.interval_value = value
        return self

    def minutes(self, value: Optional[Union[int, float]] = None) -> Schedule:
        self.mode = "interval"
        self.interval_unit = "minutes"
        if value is not None:
            self.interval_value = value
        return self

    def hours(self, value: Optional[Union[int, float]] = None) -> Schedule:
        self.mode = "interval"
        self.interval_unit = "hours"
        if value is not None:
            self.interval_value = value
        return self

    def days(self, value: Optional[Union[int, float]] = None) -> Schedule:
        self.mode = "interval"
        self.interval_unit = "days"
        if value is not None:
            self.interval_value = value
        return self

    # Алиасы
    def secondly(self) -> Schedule:
        return self.every(1).seconds()

    def minutely(self) -> Schedule:
        return self.every(1).minutes()

    def hourly(self) -> Schedule:
        return self.every(1).hours()

    def daily(self) -> Schedule:
        self.mode = "daily"
        self.interval_unit = "days"
        self.interval_value = 1
        return self

    def weekly(self) -> Schedule:
        self.mode = "weekly"
        self.interval_unit = "weeks"
        self.interval_value = 1
        return self

    def monthly(self) -> Schedule:
        self.mode = "monthly"
        return self

    # =========================================================================
    # 2. Разовые и отложенные запуски
    # =========================================================================

    def once(self, date_str: Optional[str] = None, at_time: Optional[str] = None) -> Schedule:
        """Разовый запуск в определенную дату/время."""
        self.mode = "once"
        self.date = date_str
        self.at_time = at_time
        return self

    def delay(self, value: Union[int, float], unit: str = "seconds") -> Schedule:
        """Отложенный разовый запуск через N секунд/минут."""
        self.mode = "delay"
        self.interval_value = value
        self.interval_unit = unit
        return self

    def on_startup(self) -> Schedule:
        """Срабатывание при инициализации планировщика/приложения."""
        self.mode = "on_startup"
        return self

    # =========================================================================
    # 3. Модификаторы фильтрации (время, дни, даты)
    # =========================================================================

    def at(self, time_str: str) -> Schedule:
        """Фиксирует время суток, например '09:30' или '18:00:00'."""
        self.at_time = time_str
        return self

    def on(self, *days: str) -> Schedule:
        """Указывает дни недели: .on('monday', 'friday')"""
        if self.mode == "interval":
            self.mode = "weekly"
        self.weekdays.extend([d.lower() for d in days])
        return self

    def on_days_of_month(self, *days: int) -> Schedule:
        """Указывает числа месяца: .on_days_of_month(1, 15)"""
        self.mode = "monthly"
        self.month_days.extend(days)
        return self

    def cron(self, expression: str) -> Schedule:
        """Произвольное cron-выражение."""
        self.mode = "cron"
        self.cron_expr = expression
        return self

    # =========================================================================
    # 4. Сериализация и десериализация
    # =========================================================================

    def to_dict(self) -> Dict[str, Any]:
        """Экспорт в словарь для сохранения в YAML/JSON и передачи в UI."""
        payload: Dict[str, Any] = {"mode": self.mode}

        if self.mode in ("interval", "delay"):
            payload["every"] = self.interval_value
            payload["unit"] = self.interval_unit

        if self.date:
            payload["date"] = self.date
        if self.at_time:
            payload["at"] = self.at_time
        if self.weekdays:
            payload["on"] = self.weekdays
        if self.month_days:
            payload["days_of_month"] = self.month_days
        if self.cron_expr:
            payload["expr"] = self.cron_expr

        return payload

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> Schedule:
        """Восстановление объекта расписания из словаря YAML."""
        sched = cls()
        sched.mode = data.get("mode", "interval")

        mode_unit_map = {
            "secondly": "seconds",
            "minutely": "minutes",
            "hourly": "hours",
            "daily": "days",
            "weekly": "weeks",
        }
        if sched.mode in mode_unit_map:
            sched.interval_unit = mode_unit_map[sched.mode]
            sched.interval_value = 1
            sched.mode = "interval"
        else:
            sched.interval_unit = data.get("unit")
            sched.interval_value = data.get("every", data.get("in", 1))

        sched.date = data.get("date")
        sched.at_time = data.get("at")
        sched.cron_expr = data.get("expr") or data.get("cron")

        days = data.get("on") or data.get("weekdays") or []
        sched.weekdays = [days] if isinstance(days, str) else list(days)

        m_days = data.get("days_of_month") or []
        sched.month_days = [m_days] if isinstance(m_days, int) else list(m_days)

        return sched