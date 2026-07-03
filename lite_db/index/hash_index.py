"""单列哈希索引：value -> [row_id, ...]。"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from lite_db.storage.row_store import RowStore

_INDEX_VERSION = 1


class IndexError(Exception):
    """索引构建或加载错误。"""


@dataclass
class HashIndex:
    """对单列建立的哈希索引。"""

    column: str
    table_name: str
    row_count: int
    _map: dict[Any, list[int]] = field(default_factory=dict)

    @classmethod
    def build(cls, store: RowStore, column: str) -> HashIndex:
        if column not in store.column_names:
            raise IndexError(f"UnknownColumn: column {column!r} not found")

        index_map: dict[Any, list[int]] = {}
        for row_id, row in enumerate(store.rows):
            value = row[column]
            index_map.setdefault(value, []).append(row_id)

        return cls(
            column=column,
            table_name=store.table_name,
            row_count=len(store.rows),
            _map=index_map,
        )

    def distinct_key_count(self) -> int:
        return len(self._map)

    def lookup(self, value: Any) -> tuple[int, ...]:
        return tuple(self._map.get(value, ()))

    def describe(self) -> str:
        return (
            f"HashIndex(column={self.column!r}, table={self.table_name!r}, "
            f"distinct_keys={len(self._map)}, rows={self.row_count})"
        )

    def save(self, path: str | Path) -> Path:
        target = Path(path)
        payload = {
            "version": _INDEX_VERSION,
            "table_name": self.table_name,
            "column": self.column,
            "row_count": self.row_count,
            "entries": [
                {"key": _serialize_key(key), "row_ids": row_ids}
                for key, row_ids in sorted(
                    self._map.items(),
                    key=lambda item: _serialize_key(item[0]),
                )
            ],
        }
        target.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return target

    @classmethod
    def load(cls, path: str | Path, store: RowStore) -> HashIndex:
        source = Path(path)
        if not source.is_file():
            raise FileNotFoundError(f"Index file not found: {source}")

        payload = json.loads(source.read_text(encoding="utf-8"))
        if payload.get("version") != _INDEX_VERSION:
            raise IndexError(
                f"Unsupported index version: {payload.get('version')!r}"
            )

        column = payload["column"]
        table_name = payload["table_name"]
        if table_name != store.table_name:
            raise IndexError(
                f"Index table mismatch: index is for {table_name!r}, "
                f"loaded table is {store.table_name!r}"
            )
        if column not in store.column_names:
            raise IndexError(
                f"Index column {column!r} not found in loaded table"
            )

        row_count = payload["row_count"]
        if row_count != len(store.rows):
            raise IndexError(
                f"Index row count mismatch: index has {row_count}, "
                f"table has {len(store.rows)}"
            )

        index_map: dict[Any, list[int]] = {}
        for entry in payload["entries"]:
            key = _deserialize_key(entry["key"])
            row_ids = entry["row_ids"]
            index_map[key] = row_ids

        return cls(
            column=column,
            table_name=table_name,
            row_count=row_count,
            _map=index_map,
        )


def index_path_for(csv_path: str | Path, column: str) -> Path:
    """默认索引文件路径：与 CSV 同目录，名为 `{stem}.{column}.hidx`。"""
    csv_file = Path(csv_path)
    return csv_file.parent / f"{csv_file.stem}.{column}.hidx"


def load_or_build_index(
    store: RowStore,
    column: str,
    *,
    index_path: str | Path | None = None,
) -> HashIndex:
    """若索引文件存在则加载，否则从表数据构建。"""
    path = Path(index_path) if index_path is not None else index_path_for(store.path, column)
    if path.is_file():
        return HashIndex.load(path, store)
    index = HashIndex.build(store, column)
    index.save(path)
    return index


def _serialize_key(value: Any) -> str:
    if value is None:
        return "null:"
    if isinstance(value, bool):
        raise IndexError("boolean column values cannot be indexed")
    if isinstance(value, int):
        return f"int:{value}"
    if isinstance(value, float):
        return f"float:{repr(value)}"
    if isinstance(value, str):
        return f"str:{value}"
    raise IndexError(f"unsupported index key type: {type(value)!r}")


def _deserialize_key(text: str) -> Any:
    if text == "null:":
        return None
    if text.startswith("int:"):
        return int(text[4:])
    if text.startswith("float:"):
        return float(text[6:])
    if text.startswith("str:"):
        return text[4:]
    raise IndexError(f"invalid serialized index key: {text!r}")
