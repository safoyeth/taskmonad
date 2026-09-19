from __future__ import annotations
from typing import Any, Dict, List, Optional

class Schedule:
    """Человекопонятная конфигурация расписания."""
    def __init__(self):
        self.interval_unit: Optional[str] = None  # "minute", "hour", "day", "week"
        self.interval_value: int = 1
        self.at_time: Optional[str] = None        # "14:30"
        self.weekdays: List[str] = []             # ["monday", "friday"]

    def hourly(self) -> Schedule:
        self.interval_unit = "hour"
        self.interval_value = 1
        return self

    def daily(self) -> Schedule:
        self.interval_unit = "day"
        self.interval_value = 1
        return self

    def weekly(self) -> Schedule:
        self.interval_unit = "week"
        self.interval_value = 1
        return self

    def every(self, value: int = 1) -> Schedule:
        self.interval_value = value
        return self

    def minutes(self) -> Schedule:
        self.interval_unit = "minute"
        return self

    def hours(self) -> Schedule:
        self.interval_unit = "hour"
        return self

    def days(self) -> Schedule:
        self.interval_unit = "day"
        return self

    def at(self, time_str: str) -> Schedule:
        self.at_time = time_str
        return self

    def on(self, *days: str) -> Schedule:
        self.weekdays.extend([d.lower() for d in days])
        return self

    def to_dict(self) -> Dict[str, Any]:
        return {
            "unit": self.interval_unit,
            "every": self.interval_value,
            "at": self.at_time,
            "weekdays": self.weekdays,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> Schedule:
        sched = cls()
        sched.interval_unit = data.get("unit")
        sched.interval_value = data.get("every", 1)
        sched.at_time = data.get("at")
        sched.weekdays = data.get("weekdays", [])
        return sched