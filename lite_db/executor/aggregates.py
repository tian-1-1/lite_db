"""聚合函数求值。"""

from __future__ import annotations

from typing import Any

from lite_db.executor.errors import QueryError
from lite_db.parser.ast import AggregateExpr, AggregateFunc
from lite_db.storage.column_store import ColumnStore
from lite_db.storage.table_store import TableStore
from lite_db.types import ValueType


def compute_aggregate(
    expr: AggregateExpr,
    rows: list[dict[str, Any]],
    store: TableStore,
) -> int | float | str | None:
    if expr.column is not None and expr.column not in store.column_names:
        raise QueryError(f"UnknownColumn: column {expr.column!r} not found")

    if expr.func is AggregateFunc.COUNT:
        return _count(expr, rows)
    if expr.func is AggregateFunc.SUM:
        return _sum(expr, rows, store)
    if expr.func is AggregateFunc.AVG:
        return _avg(expr, rows, store)
    if expr.func is AggregateFunc.MAX:
        return _max(expr, rows, store)
    if expr.func is AggregateFunc.MIN:
        return _min(expr, rows, store)
    raise QueryError(f"UnsupportedFeature: aggregate {expr.func.value} is not supported")


def _count(expr: AggregateExpr, rows: list[dict[str, Any]]) -> int:
    if expr.column is None:
        return len(rows)
    return sum(1 for row in rows if row[expr.column] is not None)


def _sum(
    expr: AggregateExpr,
    rows: list[dict[str, Any]],
    store: TableStore,
) -> float | None:
    values = _numeric_values(expr, rows, store)
    if not values:
        return None
    return float(sum(values))


def _avg(
    expr: AggregateExpr,
    rows: list[dict[str, Any]],
    store: TableStore,
) -> float | None:
    values = _numeric_values(expr, rows, store)
    if not values:
        return None
    return float(sum(values)) / len(values)


def _max(
    expr: AggregateExpr,
    rows: list[dict[str, Any]],
    store: TableStore,
) -> Any:
    assert expr.column is not None
    values = [row[expr.column] for row in rows if row[expr.column] is not None]
    if not values:
        return None
    column_type = store.column_types[expr.column]
    if column_type is ValueType.STRING:
        return max(values)
    return max(float(value) for value in values)


def _min(
    expr: AggregateExpr,
    rows: list[dict[str, Any]],
    store: TableStore,
) -> Any:
    assert expr.column is not None
    values = [row[expr.column] for row in rows if row[expr.column] is not None]
    if not values:
        return None
    column_type = store.column_types[expr.column]
    if column_type is ValueType.STRING:
        return min(values)
    return min(float(value) for value in values)


def _numeric_values(
    expr: AggregateExpr,
    rows: list[dict[str, Any]],
    store: TableStore,
) -> list[float]:
    assert expr.column is not None
    column_type = store.column_types[expr.column]
    if column_type is ValueType.STRING:
        raise QueryError(
            f"TypeError: aggregate {expr.func.value} requires numeric column, "
            f"got STRING column {expr.column!r}"
        )

    values: list[float] = []
    for row in rows:
        value = row[expr.column]
        if value is None:
            continue
        values.append(float(value))
    return values


def compute_numeric_aggregate_from_column(
    expr: AggregateExpr,
    store: ColumnStore,
) -> float | None:
    """列存快速路径：只读取目标列并计算 SUM/AVG。"""
    assert expr.column is not None
    if expr.column not in store.column_names:
        raise QueryError(f"UnknownColumn: column {expr.column!r} not found")

    column_type = store.column_types[expr.column]
    if column_type is ValueType.STRING:
        raise QueryError(
            f"TypeError: aggregate {expr.func.value} requires numeric column, "
            f"got STRING column {expr.column!r}"
        )

    values: list[float] = []
    for value in store.get_column(expr.column):
        if value is None:
            continue
        values.append(float(value))

    if not values:
        return None
    if expr.func is AggregateFunc.SUM:
        return float(sum(values))
    if expr.func is AggregateFunc.AVG:
        return float(sum(values)) / len(values)
    raise QueryError(
        f"UnsupportedFeature: column fast path does not support {expr.func.value}"
    )
