"""从 LLM 回复中提取 SQL。"""

from __future__ import annotations

import re

from lite_db.nl2sql.errors import Nl2SqlExtractError

_SQL_FENCE_RE = re.compile(
    r"```(?:sql)?\s*(.*?)\s*```",
    re.IGNORECASE | re.DOTALL,
)
_SELECT_STMT_RE = re.compile(
    r"(SELECT\b.+?;?)\s*$",
    re.IGNORECASE | re.DOTALL,
)


def extract_sql(text: str) -> str:
    """从模型输出中提取单条 SELECT 语句。"""
    cleaned = text.strip()
    if not cleaned:
        raise Nl2SqlExtractError("模型回复为空")

    fence_match = _SQL_FENCE_RE.search(cleaned)
    if fence_match:
        candidate = fence_match.group(1).strip()
        return _normalize_sql(candidate)

    for line in cleaned.splitlines():
        stripped = line.strip()
        if stripped.upper().startswith("SELECT"):
            return _normalize_sql(stripped)

    select_match = _SELECT_STMT_RE.search(cleaned)
    if select_match:
        return _normalize_sql(select_match.group(1))

    raise Nl2SqlExtractError(
        "无法从模型回复中提取 SQL，请重试或改用更明确的问法"
    )


def _normalize_sql(sql: str) -> str:
    sql = sql.strip().strip("`").strip()
    if sql.endswith(";"):
        sql = sql[:-1].strip()
    if not sql.upper().startswith("SELECT"):
        raise Nl2SqlExtractError(f"提取到的内容不是 SELECT 语句: {sql!r}")
    return sql
