"""表数据访问协议（行存 / 列存共用）。"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Iterator, Protocol

from lite_db.types import ValueType


class TableStore(Protocol):
    """Executor 依赖的最小存储接口。"""

    path: Path
    table_name: str
    column_names: list[str]
    column_types: dict[str, ValueType]

    def __len__(self) -> int: ...

    def iter_rows(self) -> Iterator[dict[str, Any]]: ...

    def get_row(self, row_id: int) -> dict[str, Any]: ...

    def describe(self) -> str: ...
