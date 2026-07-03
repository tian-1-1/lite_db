"""SQL 解析错误。"""

from __future__ import annotations


class SqlSyntaxError(SyntaxError):
    """SQL 语法错误。"""

    def __init__(self, message: str, *, pos: int | None = None) -> None:
        if pos is not None:
            message = f"{message} (at position {pos})"
        super().__init__(message)
        self.pos = pos
