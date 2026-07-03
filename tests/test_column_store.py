"""列式存储测试。"""

from pathlib import Path

import pytest

from lite_db.executor import execute_query
from lite_db.parser import parse_sql
from lite_db.storage import ColumnStore, RowStore


@pytest.fixture
def tiny_csv(tmp_path: Path) -> Path:
    csv_path = tmp_path / "items.csv"
    csv_path.write_text(
        "id,name,score\n1,Alice,10\n2,Bob,20\n3,Carol,\n",
        encoding="utf-8",
    )
    return csv_path


def test_build_and_load_column_store(tiny_csv: Path):
    built = ColumnStore.build_from_csv(tiny_csv)
    assert built.row_count == 3
    assert built.get_column("score") == [10, 20, None]

    loaded = ColumnStore.load(tiny_csv)
    assert loaded.get_column("name") == ["Alice", "Bob", "Carol"]


def test_iter_rows_matches_row_store(tiny_csv: Path):
    row_store = RowStore.from_csv(tiny_csv)
    column_store = ColumnStore.build_from_csv(tiny_csv)

    assert list(row_store.iter_rows()) == list(column_store.iter_rows())


def test_write_column_updates_file(tiny_csv: Path):
    store = ColumnStore.build_from_csv(tiny_csv)
    store.write_column("score", [100, 200, 300])
    reloaded = ColumnStore.load(tiny_csv)
    assert reloaded.get_column("score") == [100, 200, 300]


def test_sum_avg_column_fast_path(tiny_csv: Path):
    column_store = ColumnStore.build_from_csv(tiny_csv)
    query = parse_sql("SELECT SUM(score), AVG(score) FROM items")
    result = execute_query(column_store, query)

    assert result.used_column_fast_path is True
    assert result.rows[0]["SUM(score)"] == 30.0
    assert result.rows[0]["AVG(score)"] == 15.0


def test_select_star_on_column_store(tiny_csv: Path):
    column_store = ColumnStore.build_from_csv(tiny_csv)
    query = parse_sql("SELECT * FROM items")
    result = execute_query(column_store, query)

    assert len(result.rows) == 3
    assert result.columns == ("id", "name", "score")


def test_row_and_column_aggregate_same_result(tiny_csv: Path):
    sql = "SELECT SUM(score), AVG(score) FROM items"
    query = parse_sql(sql)
    row_result = execute_query(RowStore.from_csv(tiny_csv), query)
    col_result = execute_query(ColumnStore.build_from_csv(tiny_csv), query)
    assert row_result.rows == col_result.rows
