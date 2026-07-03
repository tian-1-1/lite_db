"""查询执行器测试（Day 4：WHERE + 投影）。"""

from pathlib import Path

import pytest

from lite_db.executor import QueryError, execute_query, format_result
from lite_db.parser import ComparisonOp, parse_sql
from lite_db.storage import RowStore


DATA_DIR = Path(__file__).resolve().parent.parent / "data"
SAMPLE_CSV = DATA_DIR / "sample.csv"


@pytest.fixture
def sample_store() -> RowStore:
    if not SAMPLE_CSV.is_file():
        pytest.skip("data/sample.csv 不存在")
    return RowStore.from_csv(SAMPLE_CSV)


def test_where_age_gt_25(sample_store: RowStore):
    query = parse_sql("SELECT name FROM sample WHERE age > 25")
    result = execute_query(sample_store, query)

    assert result.columns == ("name",)
    names = {row["name"] for row in result.rows}
    assert names == {"Alice", "Bob", "David", "Eve"}
    assert "Carol" not in names


def test_where_city_equals(sample_store: RowStore):
    query = parse_sql("SELECT name, city FROM sample WHERE city = 'Beijing'")
    result = execute_query(sample_store, query)

    assert len(result.rows) == 2
    assert all(row["city"] == "Beijing" for row in result.rows)


def test_select_star_without_where(sample_store: RowStore):
    query = parse_sql("SELECT * FROM sample")
    result = execute_query(sample_store, query)

    assert result.columns == tuple(sample_store.column_names)
    assert len(result.rows) == len(sample_store)


def test_not_equal_operator(sample_store: RowStore):
    query = parse_sql("SELECT name FROM sample WHERE city <> 'Beijing'")
    result = execute_query(sample_store, query)

    names = {row["name"] for row in result.rows}
    assert names == {"Bob", "Carol", "Eve"}


def test_unknown_column_in_where(sample_store: RowStore):
    query = parse_sql("SELECT name FROM sample WHERE missing = 1")
    with pytest.raises(QueryError, match="UnknownColumn"):
        execute_query(sample_store, query)


def test_type_mismatch(sample_store: RowStore):
    query = parse_sql("SELECT name FROM sample WHERE age = 'twenty'")
    with pytest.raises(QueryError, match="TypeError"):
        execute_query(sample_store, query)


def test_format_result_table():
    query = parse_sql("SELECT name FROM sample WHERE age > 25")
    store = RowStore.from_csv(SAMPLE_CSV)
    text = format_result(execute_query(store, query))
    assert "name" in text
    assert "Alice" in text


def test_where_and(sample_store: RowStore):
    query = parse_sql(
        "SELECT name FROM sample WHERE age > 25 AND city = 'Beijing'"
    )
    result = execute_query(sample_store, query)

    names = {row["name"] for row in result.rows}
    assert names == {"Alice", "David"}


def test_where_or(sample_store: RowStore):
    query = parse_sql(
        "SELECT name FROM sample WHERE city = 'Beijing' OR city = 'Chengdu'"
    )
    result = execute_query(sample_store, query)

    names = {row["name"] for row in result.rows}
    assert names == {"Alice", "David", "Carol"}


def test_and_or_precedence(sample_store: RowStore):
    query = parse_sql(
        "SELECT name FROM sample WHERE age > 30 OR city = 'Chengdu' AND salary < 7000"
    )
    result = execute_query(sample_store, query)

    names = {row["name"] for row in result.rows}
    assert names == {"Bob", "David", "Carol"}


def test_parentheses_change_result(sample_store: RowStore):
    without_parens = parse_sql(
        "SELECT name FROM sample WHERE salary > 10000 OR city = 'Chengdu' AND age < 25"
    )
    with_parens = parse_sql(
        "SELECT name FROM sample WHERE (salary > 10000 OR city = 'Chengdu') AND age < 25"
    )

    names_without = {row["name"] for row in execute_query(sample_store, without_parens).rows}
    names_with = {row["name"] for row in execute_query(sample_store, with_parens).rows}

    assert names_without == {"Bob", "Carol", "David"}
    assert names_with == {"Carol"}


def test_order_by_salary_desc(sample_store: RowStore):
    query = parse_sql("SELECT name, salary FROM sample ORDER BY salary DESC")
    result = execute_query(sample_store, query)

    assert [row["name"] for row in result.rows] == [
        "David",
        "Bob",
        "Eve",
        "Alice",
        "Carol",
    ]


def test_order_by_multiple_columns(sample_store: RowStore):
    query = parse_sql(
        "SELECT name, city, age FROM sample ORDER BY city ASC, age DESC"
    )
    result = execute_query(sample_store, query)

    assert [(row["city"], row["age"]) for row in result.rows] == [
        ("Beijing", 41),
        ("Beijing", 28),
        ("Chengdu", 22),
        ("Shanghai", 35),
        ("Shanghai", 30),
    ]


def test_unknown_order_by_column(sample_store: RowStore):
    query = parse_sql("SELECT name FROM sample ORDER BY missing")
    with pytest.raises(QueryError, match="UnknownColumn"):
        execute_query(sample_store, query)


def test_count_star(sample_store: RowStore):
    query = parse_sql("SELECT COUNT(*) FROM sample")
    result = execute_query(sample_store, query)
    assert result.columns == ("COUNT(*)",)
    assert result.rows[0]["COUNT(*)"] == 5


def test_count_with_where(sample_store: RowStore):
    query = parse_sql("SELECT COUNT(*) FROM sample WHERE city = 'Beijing'")
    result = execute_query(sample_store, query)
    assert result.rows[0]["COUNT(*)"] == 2


def test_sum_avg_max_min(sample_store: RowStore):
    query = parse_sql(
        "SELECT SUM(salary), AVG(age), MAX(salary), MIN(age) FROM sample"
    )
    result = execute_query(sample_store, query)
    row = result.rows[0]
    assert row["SUM(salary)"] == 52100.5
    assert row["AVG(age)"] == 31.2
    assert row["MAX(salary)"] == 15000.0
    assert row["MIN(age)"] == 22


def test_sum_on_string_column(sample_store: RowStore):
    query = parse_sql("SELECT SUM(name) FROM sample")
    with pytest.raises(QueryError, match="TypeError"):
        execute_query(sample_store, query)


def test_count_column_ignores_nulls(tmp_path: Path):
    csv_path = tmp_path / "nulls.csv"
    csv_path.write_text("id,score\n1,10\n2,\n3,30\n", encoding="utf-8")
    store = RowStore.from_csv(csv_path)
    query = parse_sql("SELECT COUNT(score) FROM nulls")
    result = execute_query(store, query)
    assert result.rows[0]["COUNT(score)"] == 2


def test_empty_filter_count_is_zero(tmp_path: Path):
    csv_path = tmp_path / "tiny.csv"
    csv_path.write_text("id,name\n1,Alice\n", encoding="utf-8")
    store = RowStore.from_csv(csv_path)
    query = parse_sql("SELECT COUNT(*) FROM tiny WHERE name = 'Bob'")
    result = execute_query(store, query)
    assert result.rows[0]["COUNT(*)"] == 0


def test_empty_filter_sum_is_null(tmp_path: Path):
    csv_path = tmp_path / "tiny.csv"
    csv_path.write_text("id,name\n1,Alice\n", encoding="utf-8")
    store = RowStore.from_csv(csv_path)
    query = parse_sql("SELECT SUM(id) FROM tiny WHERE name = 'Bob'")
    result = execute_query(store, query)
    assert result.rows[0]["SUM(id)"] is None

