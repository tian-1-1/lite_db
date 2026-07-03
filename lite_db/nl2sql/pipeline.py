"""自然语言转 SQL 端到端流程。"""

from __future__ import annotations

from dataclasses import dataclass

from lite_db.nl2sql.client import complete
from lite_db.nl2sql.errors import Nl2SqlError
from lite_db.nl2sql.extractor import extract_sql
from lite_db.nl2sql.prompt import DEFAULT_MODEL, build_messages
from lite_db.nl2sql.validator import validate_sql
from lite_db.storage.table_store import TableStore


@dataclass(frozen=True, slots=True)
class Nl2SqlResult:
    """NL2SQL 转换结果。"""

    question: str
    sql: str
    model: str
    raw_response: str


def nl_to_sql(
    store: TableStore,
    question: str,
    *,
    model: str = DEFAULT_MODEL,
    api_key: str | None = None,
    llm_complete=complete,
) -> Nl2SqlResult:
    """自然语言问句 → 校验通过的 SQL。"""
    text = question.strip()
    if not text:
        raise Nl2SqlError("自然语言问句不能为空")

    messages = build_messages(store, text)
    raw = llm_complete(messages, model=model, api_key=api_key)
    sql = extract_sql(raw)
    validated = validate_sql(store, sql)
    return Nl2SqlResult(
        question=text,
        sql=validated,
        model=model,
        raw_response=raw,
    )
