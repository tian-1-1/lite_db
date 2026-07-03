"""列类型与单元格值解析。"""

from __future__ import annotations

from enum import Enum
from typing import Any


class ValueType(str, Enum):
    INTEGER = "INTEGER"
    FLOAT = "FLOAT"
    STRING = "STRING"


def is_null_literal(raw: str) -> bool:
    return raw.strip() == "" or raw.strip().upper() == "NULL"


def is_int_literal(raw: str) -> bool:
    text = raw.strip()
    if not text or text[0] not in "+-":
        if not text.isdigit():
            return False
        return True
    sign = text[0]
    body = text[1:]
    return body.isdigit() and body != ""


def is_float_literal(raw: str) -> bool:
    text = raw.strip()
    if is_int_literal(text):
        return True
    try:
        float(text)
    except ValueError:
        return False
    return True


def infer_column_type(raw_values: list[str]) -> ValueType:
    """根据列中所有原始字符串推断列类型。"""
    kind = "integer"

    for raw in raw_values:
        if is_null_literal(raw):
            continue
        if kind == "string":
            continue
        if is_int_literal(raw):
            continue
        if is_float_literal(raw):
            kind = "float"
            continue
        kind = "string"

    if kind == "string":
        return ValueType.STRING
    if kind == "float":
        return ValueType.FLOAT
    return ValueType.INTEGER


def parse_cell(raw: str, column_type: ValueType) -> Any:
    """将 CSV 原始字符串解析为 Python 值。"""
    if is_null_literal(raw):
        return None

    text = raw.strip()
    if column_type is ValueType.INTEGER:
        return int(text)
    if column_type is ValueType.FLOAT:
        return float(text)
    return text
