"""查询执行器。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from lite_db.executor.aggregates import (
    compute_aggregate,
    compute_numeric_aggregate_from_column,
)
from lite_db.executor.errors import QueryError
from lite_db.executor.evaluator import evaluate_where
from lite_db.executor.index_scan import extract_indexable_eq
from lite_db.index.hash_index import HashIndex
from lite_db.parser.ast import AggregateExpr, AggregateFunc, ColumnRef, OrderItem, SelectQuery, Star
from lite_db.storage.column_store import ColumnStore
from lite_db.storage.table_store import TableStore


@dataclass(frozen=True, slots=True)
class QueryResult:
    columns: tuple[str, ...]
    rows: tuple[dict[str, Any], ...]
    used_index: str | None = None
    used_column_fast_path: bool = False


def execute_query(
    store: TableStore,
    query: SelectQuery,
    *,
    indices: dict[str, HashIndex] | None = None,
    force_full_scan: bool = False,
) -> QueryResult:
    if query.table_name != store.table_name:
        raise QueryError(
            f"UnknownTable: table {query.table_name!r} does not match loaded table "
            f"{store.table_name!r}"
        )

    active_indices = None if force_full_scan else indices

    if query.is_aggregate:
        return _execute_aggregate(store, query, active_indices, force_full_scan)

    output_columns = _resolve_output_columns(store, query)
    filtered_rows: list[dict[str, Any]] = []
    used_index: str | None = None

    for row, index_column in _iter_candidate_rows(store, query.where, active_indices):
        if index_column is not None and used_index is None:
            used_index = index_column
        if query.where is not None and not evaluate_where(row, query.where):
            continue
        filtered_rows.append(_project_row(row, output_columns))

    sorted_rows = _sort_rows(filtered_rows, query.order_by, output_columns)
    return QueryResult(
        columns=output_columns,
        rows=tuple(sorted_rows),
        used_index=used_index,
    )


def _execute_aggregate(
    store: TableStore,
    query: SelectQuery,
    indices: dict[str, HashIndex] | None,
    force_full_scan: bool,
) -> QueryResult:
    if (
        isinstance(store, ColumnStore)
        and query.where is None
        and not query.order_by
        and _can_use_column_fast_path(query)
    ):
        return _execute_aggregate_column_fast(store, query)

    filtered_rows: list[dict[str, Any]] = []
    used_index: str | None = None

    for row, index_column in _iter_candidate_rows(store, query.where, indices):
        if index_column is not None and used_index is None:
            used_index = index_column
        if query.where is not None and not evaluate_where(row, query.where):
            continue
        filtered_rows.append(row)

    output_columns = tuple(query.output_labels())
    result_row: dict[str, Any] = {}
    for item in query.select_list:
        if isinstance(item, AggregateExpr):
            label = item.output_name()
            result_row[label] = compute_aggregate(item, filtered_rows, store)

    rows = [result_row]
    sorted_rows = _sort_rows(rows, query.order_by, output_columns)
    return QueryResult(
        columns=output_columns,
        rows=tuple(sorted_rows),
        used_index=used_index,
    )


def _execute_aggregate_column_fast(
    store: ColumnStore,
    query: SelectQuery,
) -> QueryResult:
    output_columns = tuple(query.output_labels())
    result_row: dict[str, Any] = {}
    for item in query.select_list:
        if isinstance(item, AggregateExpr):
            label = item.output_name()
            if item.func in {AggregateFunc.SUM, AggregateFunc.AVG}:
                result_row[label] = compute_numeric_aggregate_from_column(item, store)
            else:
                raise QueryError(
                    f"UnsupportedFeature: column fast path does not support {item.func.value}"
                )
    return QueryResult(
        columns=output_columns,
        rows=(result_row,),
        used_column_fast_path=True,
    )


def _can_use_column_fast_path(query: SelectQuery) -> bool:
    if not query.select_list:
        return False
    for item in query.select_list:
        if not isinstance(item, AggregateExpr):
            return False
        if item.func not in {AggregateFunc.SUM, AggregateFunc.AVG}:
            return False
        if item.column is None:
            return False
    return True


def _iter_candidate_rows(
    store: TableStore,
    where: Any,
    indices: dict[str, HashIndex] | None,
):
    if where is None or not indices:
        for row in store.iter_rows():
            yield row, None
        return

    indexable = extract_indexable_eq(where, indices)
    if indexable is None:
        for row in store.iter_rows():
            yield row, None
        return

    column, value = indexable
    row_ids = indices[column].lookup(value)
    for row_id in row_ids:
        yield store.get_row(row_id), column


def format_result(result: QueryResult) -> str:
    if not result.rows:
        return "(empty result)"

    headers = list(result.columns)
    rendered_rows = [
        [_format_cell(row.get(column)) for column in headers] for row in result.rows
    ]
    widths = [
        max(len(headers[index]), *(len(row[index]) for row in rendered_rows))
        for index in range(len(headers))
    ]

    def render_line(cells: list[str]) -> str:
        return " | ".join(
            cell.ljust(widths[index]) for index, cell in enumerate(cells)
        )

    separator = "-+-".join("-" * width for width in widths)
    lines = [render_line(headers), separator]
    lines.extend(render_line(row) for row in rendered_rows)
    return "\n".join(lines)


def _resolve_output_columns(store: TableStore, query: SelectQuery) -> tuple[str, ...]:
    if query.selects_all:
        return tuple(store.column_names)

    columns: list[str] = []
    for item in query.select_list:
        if isinstance(item, Star):
            continue
        if isinstance(item, ColumnRef):
            if item.name not in store.column_names:
                raise QueryError(f"UnknownColumn: column {item.name!r} not found")
            columns.append(item.name)
    return tuple(columns)


def _project_row(row: dict[str, Any], columns: tuple[str, ...]) -> dict[str, Any]:
    return {column: row[column] for column in columns}


def _sort_rows(
    rows: list[dict[str, Any]],
    order_by: tuple[OrderItem, ...],
    valid_columns: tuple[str, ...],
) -> list[dict[str, Any]]:
    if not order_by:
        return rows

    for item in order_by:
        if item.column not in valid_columns:
            raise QueryError(f"UnknownColumn: column {item.column!r} not found")

    sorted_rows = rows
    for item in reversed(order_by):
        sorted_rows = sorted(
            sorted_rows,
            key=lambda row: _sort_key_value(row[item.column]),
            reverse=item.order.value == "DESC",
        )
    return sorted_rows


def _sort_key_value(value: Any) -> tuple[int, float | str]:
    if value is None:
        return (0, "")
    if isinstance(value, str):
        return (1, value)
    return (1, float(value))


def _format_cell(value: Any) -> str:
    if value is None:
        return "NULL"
    return str(value)
