"""校验 NL2SQL 生成的 SQL 是否符合引擎子集与当前表 schema。"""

from __future__ import annotations

import re

from lite_db.nl2sql.errors import Nl2SqlValidationError
from lite_db.parser.ast import (
    AggregateExpr,
    AndExpr,
    BoolExpr,
    ColumnRef,
    ComparisonExpr,
    OrExpr,
    SelectQuery,
)
from lite_db.parser import SqlSyntaxError, parse_sql
from lite_db.storage.table_store import TableStore

_FORBIDDEN_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"\bJOIN\b", re.IGNORECASE), "JOIN"),
    (re.compile(r"\bGROUP\s+BY\b", re.IGNORECASE), "GROUP BY"),
    (re.compile(r"\bHAVING\b", re.IGNORECASE), "HAVING"),
    (re.compile(r"\bLIMIT\b", re.IGNORECASE), "LIMIT"),
    (re.compile(r"\bOFFSET\b", re.IGNORECASE), "OFFSET"),
    (re.compile(r"\bLIKE\b", re.IGNORECASE), "LIKE"),
    (re.compile(r"\bBETWEEN\b", re.IGNORECASE), "BETWEEN"),
    (re.compile(r"\bUNION\b", re.IGNORECASE), "UNION"),
    (re.compile(r"\bDISTINCT\b", re.IGNORECASE), "DISTINCT"),
    (re.compile(r"\bIS\s+NULL\b", re.IGNORECASE), "IS NULL"),
    (re.compile(r"\(\s*SELECT\b", re.IGNORECASE), "subquery"),
    (re.compile(r"\bIN\s*\(", re.IGNORECASE), "IN (...)"),
    (re.compile(r"\bAS\b", re.IGNORECASE), "AS alias"),
]


def validate_sql(store: TableStore, sql: str) -> str:
    """校验 SQL；通过则返回规范化后的原 SQL 字符串。"""
    normalized = sql.strip()
    if not normalized:
        raise Nl2SqlValidationError("SQL 为空")

    for pattern, label in _FORBIDDEN_PATTERNS:
        if pattern.search(normalized):
            raise Nl2SqlValidationError(f"不支持 {label} 语法")

    try:
        query = parse_sql(normalized)
    except SqlSyntaxError as exc:
        raise Nl2SqlValidationError(str(exc)) from exc

    if query.table_name.lower() != store.table_name.lower():
        raise Nl2SqlValidationError(
            f"表名不匹配: 期望 {store.table_name!r}，得到 {query.table_name!r}"
        )

    allowed = set(store.column_names)
    for name in _referenced_columns(query):
        if name not in allowed:
            raise Nl2SqlValidationError(f"未知列: {name!r}")

    return normalized


def _referenced_columns(query: SelectQuery) -> set[str]:
    names: set[str] = set()
    for item in query.select_list:
        if isinstance(item, ColumnRef):
            names.add(item.name)
        elif isinstance(item, AggregateExpr) and item.column is not None:
            names.add(item.column)
    if query.where is not None:
        names.update(_bool_expr_columns(query.where))
    for order_item in query.order_by:
        names.add(order_item.column)
    return names


def _bool_expr_columns(expr: BoolExpr) -> set[str]:
    if isinstance(expr, ComparisonExpr):
        return {expr.column}
    if isinstance(expr, AndExpr):
        return _bool_expr_columns(expr.left) | _bool_expr_columns(expr.right)
    if isinstance(expr, OrExpr):
        return _bool_expr_columns(expr.left) | _bool_expr_columns(expr.right)
    raise TypeError(f"unexpected bool expr: {type(expr)!r}")
