"""SQL 抽象语法树（AST）。"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Union


class ComparisonOp(str, Enum):
    EQ = "="
    NE = "!="
    GT = ">"
    LT = "<"
    GE = ">="
    LE = "<="


@dataclass(frozen=True, slots=True)
class Star:
    """SELECT * 中的星号。"""


@dataclass(frozen=True, slots=True)
class ColumnRef:
    """列引用。"""

    name: str


LiteralValue = Union[int, float, str, None]


class AggregateFunc(str, Enum):
    COUNT = "COUNT"
    SUM = "SUM"
    AVG = "AVG"
    MAX = "MAX"
    MIN = "MIN"


@dataclass(frozen=True, slots=True)
class AggregateExpr:
    """SELECT 列表中的聚合表达式。"""

    func: AggregateFunc
    column: str | None = None

    def output_name(self) -> str:
        if self.column is None:
            return f"{self.func.value}(*)"
        return f"{self.func.value}({self.column})"


SelectItem = Union[Star, ColumnRef, AggregateExpr]


@dataclass(frozen=True, slots=True)
class ComparisonExpr:
    """WHERE 中的比较条件。"""

    column: str
    op: ComparisonOp
    value: LiteralValue


@dataclass(frozen=True, slots=True)
class AndExpr:
    """WHERE 中的 AND 组合。"""

    left: BoolExpr
    right: BoolExpr


@dataclass(frozen=True, slots=True)
class OrExpr:
    """WHERE 中的 OR 组合。"""

    left: BoolExpr
    right: BoolExpr


BoolExpr = Union[ComparisonExpr, AndExpr, OrExpr]


class SortOrder(str, Enum):
    ASC = "ASC"
    DESC = "DESC"


@dataclass(frozen=True, slots=True)
class OrderItem:
    """ORDER BY 中的单列排序项。"""

    column: str
    order: SortOrder = SortOrder.ASC


@dataclass(frozen=True, slots=True)
class SelectQuery:
    """单表 SELECT 查询。"""

    select_list: tuple[SelectItem, ...]
    table_name: str
    where: BoolExpr | None = None
    order_by: tuple[OrderItem, ...] = ()

    @property
    def selects_all(self) -> bool:
        return len(self.select_list) == 1 and isinstance(self.select_list[0], Star)

    @property
    def is_aggregate(self) -> bool:
        return any(isinstance(item, AggregateExpr) for item in self.select_list)

    def column_names(self) -> list[str]:
        if self.selects_all:
            raise ValueError("SELECT * does not expose explicit column names")
        return [item.name for item in self.select_list if isinstance(item, ColumnRef)]

    def output_labels(self) -> list[str]:
        if self.selects_all:
            raise ValueError("SELECT * does not expose output labels")
        labels: list[str] = []
        for item in self.select_list:
            if isinstance(item, ColumnRef):
                labels.append(item.name)
            elif isinstance(item, AggregateExpr):
                labels.append(item.output_name())
        return labels
