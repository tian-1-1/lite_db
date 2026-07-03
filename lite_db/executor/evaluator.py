"""WHERE 条件求值。"""

from __future__ import annotations

from lite_db.executor.errors import QueryError
from lite_db.parser.ast import AndExpr, BoolExpr, ComparisonExpr, ComparisonOp, OrExpr


def evaluate_where(row: dict[str, object], expr: BoolExpr) -> bool:
    if isinstance(expr, ComparisonExpr):
        return evaluate_comparison(row, expr)
    if isinstance(expr, AndExpr):
        return evaluate_where(row, expr.left) and evaluate_where(row, expr.right)
    if isinstance(expr, OrExpr):
        return evaluate_where(row, expr.left) or evaluate_where(row, expr.right)
    raise QueryError(f"UnsupportedFeature: unsupported WHERE expression {type(expr)!r}")


def evaluate_comparison(row: dict[str, object], expr: ComparisonExpr) -> bool:
    if expr.column not in row:
        raise QueryError(f"UnknownColumn: column {expr.column!r} not found")

    left = row[expr.column]
    right = expr.value

    if left is None or right is None:
        return False

    if isinstance(left, str) or isinstance(right, str):
        if not isinstance(left, str) or not isinstance(right, str):
            raise QueryError(
                f"TypeError: cannot compare column {expr.column!r} "
                f"with literal of incompatible type"
            )
        return _compare_values(left, right, expr.op)

    if isinstance(left, bool) or isinstance(right, bool):
        raise QueryError("TypeError: boolean comparison is not supported")

    left_number = float(left)
    right_number = float(right)
    return _compare_values(left_number, right_number, expr.op)


def _compare_values(left: object, right: object, op: ComparisonOp) -> bool:
    if op is ComparisonOp.EQ:
        return left == right
    if op is ComparisonOp.NE:
        return left != right
    if op is ComparisonOp.GT:
        return left > right
    if op is ComparisonOp.LT:
        return left < right
    if op is ComparisonOp.GE:
        return left >= right
    if op is ComparisonOp.LE:
        return left <= right
    raise QueryError(f"unsupported operator {op.value}")
