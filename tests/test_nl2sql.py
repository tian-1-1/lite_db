"""NL2SQL 单元测试（Mock，不调用 DashScope API）。"""

from __future__ import annotations

from pathlib import Path

import pytest

from lite_db.nl2sql.extractor import extract_sql
from lite_db.nl2sql.pipeline import nl_to_sql
from lite_db.nl2sql.prompt import build_system_prompt
from lite_db.nl2sql.validator import validate_sql
from lite_db.parser import parse_sql
from lite_db.storage import RowStore

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
SAMPLE_CSV = DATA_DIR / "sample.csv"


@pytest.fixture
def sample_store() -> RowStore:
    if not SAMPLE_CSV.is_file():
        pytest.skip("data/sample.csv 不存在")
    return RowStore.from_csv(SAMPLE_CSV)


def test_build_system_prompt_contains_schema(sample_store: RowStore):
    prompt = build_system_prompt(sample_store)
    assert sample_store.table_name in prompt
    for name in sample_store.column_names:
        assert name in prompt
    assert "GROUP BY" in prompt
    assert "禁止" in prompt


def test_extract_sql_from_markdown_fence():
    raw = "好的，SQL 如下：\n```sql\nSELECT COUNT(*) FROM ratings\n```"
    assert extract_sql(raw) == "SELECT COUNT(*) FROM ratings"


def test_extract_sql_from_plain_line():
    raw = "SELECT AVG(rating) FROM ratings"
    assert extract_sql(raw) == "SELECT AVG(rating) FROM ratings"


def test_extract_sql_strips_trailing_semicolon():
    raw = "```sql\nSELECT * FROM sample;\n```"
    assert extract_sql(raw) == "SELECT * FROM sample"


def test_validate_rejects_join(sample_store: RowStore):
    with pytest.raises(Exception, match="JOIN"):
        validate_sql(sample_store, "SELECT * FROM sample JOIN other ON id = id")


def test_validate_rejects_unknown_column(sample_store: RowStore):
    with pytest.raises(Exception, match="未知列"):
        validate_sql(sample_store, "SELECT foo FROM sample")


def test_validate_accepts_where_query(sample_store: RowStore):
    sql = "SELECT name FROM sample WHERE age > 25"
    validated = validate_sql(sample_store, sql)
    assert validated == sql
    query = parse_sql(validated)
    assert query.table_name == "sample"


def test_nl_to_sql_with_mock_llm(sample_store: RowStore):
    def fake_complete(messages, *, model, api_key=None):
        assert any("sample" in m["content"] for m in messages)
        return "SELECT COUNT(*) FROM sample"

    result = nl_to_sql(
        sample_store,
        "一共有多少人",
        model="mock-model",
        llm_complete=fake_complete,
    )
    assert result.sql == "SELECT COUNT(*) FROM sample"
    assert result.model == "mock-model"


def test_nl_to_sql_mock_rejects_invalid_sql(sample_store: RowStore):
    def fake_complete(messages, *, model, api_key=None):
        return "SELECT name FROM sample GROUP BY city"

    with pytest.raises(Exception, match="GROUP BY"):
        nl_to_sql(
            sample_store,
            "按城市分组",
            llm_complete=fake_complete,
        )
