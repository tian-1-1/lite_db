"""列式存储：每列独立 JSON 文件 + manifest。"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterator

from lite_db.storage.row_store import RowStore
from lite_db.types import ValueType


class ColumnStoreError(Exception):
    """列存构建或加载错误。"""


_COLSTORE_VERSION = 1
_COLUMNS_DIR = "columns"


@dataclass
class ColumnStore:
    """CSV 对应的列式存储目录。"""

    path: Path
    colstore_dir: Path
    table_name: str
    column_names: list[str]
    column_types: dict[str, ValueType]
    row_count: int
    _column_cache: dict[str, list[Any]] = field(default_factory=dict)

    @classmethod
    def build_from_csv(cls, csv_path: str | Path) -> ColumnStore:
        row_store = RowStore.from_csv(csv_path)
        target_dir = colstore_path_for(csv_path)
        columns: dict[str, list[Any]] = {
            name: [row[name] for row in row_store.rows] for name in row_store.column_names
        }
        return cls._write_store(row_store.path, target_dir, row_store, columns)

    @classmethod
    def load(cls, csv_path: str | Path) -> ColumnStore:
        source = Path(csv_path)
        colstore_dir = colstore_path_for(source)
        if not colstore_dir.is_dir():
            raise FileNotFoundError(f"Column store directory not found: {colstore_dir}")

        manifest_path = colstore_dir / "manifest.json"
        if not manifest_path.is_file():
            raise ColumnStoreError(f"Missing manifest: {manifest_path}")

        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        if manifest.get("version") != _COLSTORE_VERSION:
            raise ColumnStoreError(
                f"Unsupported column store version: {manifest.get('version')!r}"
            )

        table_name = manifest["table_name"]
        row_count = manifest["row_count"]
        column_names = manifest["column_names"]
        column_types = {
            name: ValueType(manifest["column_types"][name]) for name in column_names
        }

        if table_name != source.stem:
            raise ColumnStoreError(
                f"Column store table mismatch: {table_name!r} vs {source.stem!r}"
            )

        return cls(
            path=source,
            colstore_dir=colstore_dir,
            table_name=table_name,
            column_names=column_names,
            column_types=column_types,
            row_count=row_count,
        )

    @classmethod
    def load_or_build(cls, csv_path: str | Path) -> ColumnStore:
        colstore_dir = colstore_path_for(csv_path)
        if colstore_dir.is_dir() and (colstore_dir / "manifest.json").is_file():
            return cls.load(csv_path)
        return cls.build_from_csv(csv_path)

    def clear_cache(self) -> None:
        """清空列缓存（benchmark 冷读时使用）。"""
        self._column_cache.clear()

    def get_column(self, name: str) -> list[Any]:
        if name not in self.column_names:
            raise KeyError(f"Unknown column: {name!r}")
        if name not in self._column_cache:
            self._column_cache[name] = _load_column_values(
                self.colstore_dir / _COLUMNS_DIR / f"{name}.json"
            )
        return self._column_cache[name]

    def read_column(self, name: str) -> list[Any]:
        """对外读写接口别名。"""
        return self.get_column(name)

    def write_column(self, name: str, values: list[Any]) -> None:
        """更新单列并落盘（覆盖该列文件）。"""
        if name not in self.column_names:
            raise KeyError(f"Unknown column: {name!r}")
        if len(values) != self.row_count:
            raise ColumnStoreError(
                f"Column length mismatch for {name!r}: "
                f"expected {self.row_count}, got {len(values)}"
            )
        column_path = self.colstore_dir / _COLUMNS_DIR / f"{name}.json"
        _save_column_values(column_path, values)
        self._column_cache[name] = list(values)

    def __len__(self) -> int:
        return self.row_count

    def iter_rows(self) -> Iterator[dict[str, Any]]:
        columns = {name: self.get_column(name) for name in self.column_names}
        for row_id in range(self.row_count):
            yield {
                name: columns[name][row_id] for name in self.column_names
            }

    def get_row(self, row_id: int) -> dict[str, Any]:
        if row_id < 0 or row_id >= self.row_count:
            raise IndexError(f"row_id out of range: {row_id}")
        return {name: self.get_column(name)[row_id] for name in self.column_names}

    def describe(self) -> str:
        lines = [
            f"table: {self.table_name}",
            f"csv: {self.path}",
            f"column store: {self.colstore_dir}",
            f"rows: {self.row_count}",
            "columns:",
        ]
        for name in self.column_names:
            lines.append(f"  - {name}: {self.column_types[name].value}")
        return "\n".join(lines)

    @classmethod
    def _write_store(
        cls,
        csv_path: Path,
        colstore_dir: Path,
        row_store: RowStore,
        columns: dict[str, list[Any]],
    ) -> ColumnStore:
        colstore_dir.mkdir(parents=True, exist_ok=True)
        columns_dir = colstore_dir / _COLUMNS_DIR
        columns_dir.mkdir(exist_ok=True)

        manifest = {
            "version": _COLSTORE_VERSION,
            "table_name": row_store.table_name,
            "source_csv": str(csv_path),
            "row_count": len(row_store),
            "column_names": row_store.column_names,
            "column_types": {
                name: row_store.column_types[name].value
                for name in row_store.column_names
            },
        }
        (colstore_dir / "manifest.json").write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

        for name, values in columns.items():
            _save_column_values(columns_dir / f"{name}.json", values)

        return cls(
            path=csv_path,
            colstore_dir=colstore_dir,
            table_name=row_store.table_name,
            column_names=list(row_store.column_names),
            column_types=dict(row_store.column_types),
            row_count=len(row_store),
        )


def colstore_path_for(csv_path: str | Path) -> Path:
    """默认列存目录：与 CSV 同目录，名为 `{stem}.colstore/`。"""
    csv_file = Path(csv_path)
    return csv_file.parent / f"{csv_file.stem}.colstore"


def _serialize_value(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, bool):
        raise ColumnStoreError("boolean values are not supported in column store")
    if isinstance(value, (int, float, str)):
        return value
    raise ColumnStoreError(f"unsupported column value type: {type(value)!r}")


def _save_column_values(path: Path, values: list[Any]) -> None:
    payload = [_serialize_value(value) for value in values]
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


def _load_column_values(path: Path) -> list[Any]:
    if not path.is_file():
        raise FileNotFoundError(f"Column file not found: {path}")
    raw_values = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw_values, list):
        raise ColumnStoreError(f"Invalid column file format: {path}")

    column_name = path.stem
    # 类型在 manifest 中；加载时按 manifest 的 column_types 解析更严谨。
    # 此处 values 已是 JSON 原生类型，与 RowStore 一致即可。
    return raw_values