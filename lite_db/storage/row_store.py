"""CSV 行式存储。"""

from __future__ import annotations

import csv
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterator

from lite_db.types import ValueType, infer_column_type, parse_cell


@dataclass
class RowStore:
    """将 CSV 文件加载为单表行存。"""

    path: Path
    table_name: str
    column_names: list[str]
    column_types: dict[str, ValueType]
    rows: list[dict[str, Any]] = field(default_factory=list)

    @classmethod
    def from_csv(cls, path: str | Path) -> RowStore:
        csv_path = Path(path)
        if not csv_path.is_file():
            raise FileNotFoundError(f"CSV file not found: {csv_path}")

        raw_rows = _read_raw_rows(csv_path)
        if not raw_rows:
            raise ValueError(f"CSV file is empty: {csv_path}")

        column_names = [name.strip() for name in raw_rows[0]]
        if not column_names or any(name == "" for name in column_names):
            raise ValueError("CSV header must contain non-empty column names")

        data_rows = raw_rows[1:]
        _validate_row_widths(column_names, data_rows, csv_path)

        column_types = _infer_schema(column_names, data_rows)
        rows = [_build_row(column_names, column_types, raw_row) for raw_row in data_rows]

        return cls(
            path=csv_path,
            table_name=csv_path.stem,
            column_names=column_names,
            column_types=column_types,
            rows=rows,
        )

    def __len__(self) -> int:
        return len(self.rows)

    def iter_rows(self) -> Iterator[dict[str, Any]]:
        yield from self.rows

    def get_row(self, row_id: int) -> dict[str, Any]:
        if row_id < 0 or row_id >= len(self.rows):
            raise IndexError(f"row_id out of range: {row_id}")
        return self.rows[row_id]

    def describe(self) -> str:
        lines = [
            f"table: {self.table_name}",
            f"path: {self.path}",
            f"rows: {len(self.rows)}",
            "columns:",
        ]
        for name in self.column_names:
            lines.append(f"  - {name}: {self.column_types[name].value}")
        return "\n".join(lines)


def _read_raw_rows(path: Path) -> list[list[str]]:
    with path.open(newline="", encoding="utf-8-sig") as file:
        reader = csv.reader(file)
        rows: list[list[str]] = []
        for row in reader:
            if not row or all(cell.strip() == "" for cell in row):
                continue
            rows.append(row)
        return rows


def _validate_row_widths(
    column_names: list[str],
    data_rows: list[list[str]],
    path: Path,
) -> None:
    expected = len(column_names)
    for index, row in enumerate(data_rows, start=2):
        if len(row) != expected:
            raise ValueError(
                f"Column count mismatch in {path} at line {index}: "
                f"expected {expected}, got {len(row)}"
            )


def _infer_schema(
    column_names: list[str],
    data_rows: list[list[str]],
) -> dict[str, ValueType]:
    columns: dict[str, list[str]] = {name: [] for name in column_names}
    for row in data_rows:
        for name, value in zip(column_names, row, strict=True):
            columns[name].append(value)

    return {name: infer_column_type(values) for name, values in columns.items()}


def _build_row(
    column_names: list[str],
    column_types: dict[str, ValueType],
    raw_row: list[str],
) -> dict[str, Any]:
    return {
        name: parse_cell(raw_value, column_types[name])
        for name, raw_value in zip(column_names, raw_row, strict=True)
    }
