"""索引辅助：从 WHERE 中提取可走索引的等值条件。"""

from __future__ import annotations

from typing import Any

from lite_db.index.hash_index import HashIndex
from lite_db.parser.ast import AndExpr, BoolExpr, ComparisonExpr, ComparisonOp, OrExpr


def extract_indexable_eq(
    expr: BoolExpr,
    indices: dict[str, HashIndex],
) -> tuple[str, Any] | None:
    """在 AND 树中查找第一个 indexed_col = literal（不在 OR 分支下）。"""
    if isinstance(expr, ComparisonExpr):
        if expr.op is ComparisonOp.EQ and expr.column in indices:
            return expr.column, expr.value
        return None

    if isinstance(expr, AndExpr):
        left = extract_indexable_eq(expr.left, indices)
        if left is not None:
            return left
        return extract_indexable_eq(expr.right, indices)

    if isinstance(expr, OrExpr):
        return None

    return None
