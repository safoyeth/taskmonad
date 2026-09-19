from __future__ import annotations
import copy
from dataclasses import dataclass, field
from typing import Any

@dataclass(frozen=True)
class TaskContext:
    """Иммутабельный контейнер состояния задачи."""
    data: dict[str, Any] = field(default_factory=dict)
    meta: dict[str, Any] = field(default_factory=dict)

    def set(self, key: str, value: Any) -> TaskContext:
        """Возвращает новый контекст с установленным ключом в data."""
        new_data = copy.deepcopy(self.data)
        new_data[key] = value
        return TaskContext(data=new_data, meta=self.meta)

    def update(self, new_data: dict[str, Any]) -> TaskContext:
        """Возвращает новый контекст с объединенными данными."""
        merged = copy.deepcopy(self.data)
        merged.update(new_data)
        return TaskContext(data=merged, meta=self.meta)

    def get(self, key: str, default: Any = None) -> Any:
        return self.data.get(key, default)

    def set_meta(self, key: str, value: Any) -> TaskContext:
        """Запись в системные метаданные (не сериализуется в JSON)."""
        new_meta = self.meta.copy()
        new_meta[key] = value
        return TaskContext(data=self.data, meta=new_meta)

    def get_meta(self, key: str, default: Any = None) -> Any:
        return self.meta.get(key, default)