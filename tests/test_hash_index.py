"""哈希索引测试。"""

from pathlib import Path

import pytest

from lite_db.executor import execute_query
from lite_db.index import HashIndex, IndexError, index_path_for, load_or_build_index
from lite_db.parser import parse_sql
from lite_db.storage import RowStore


DATA_DIR = Path(__file__).resolve().parent.parent / "data"
SAMPLE_CSV = DATA_DIR / "sample.csv"


@pytest.fixture
def sample_store() -> RowStore:
    if not SAMPLE_CSV.is_file():
        pytest.skip("data/sample.csv 不存在")
    return RowStore.from_csv(SAMPLE_CSV)


def test_build_and_lookup(sample_store: RowStore):
    index = HashIndex.build(sample_store, "city")
    assert index.lookup("Beijing") == (0, 3)
    assert index.lookup("Shanghai") == (1, 4)
    assert index.lookup("Unknown") == ()


def test_index_accelerates_equality_query(sample_store: RowStore):
    indices = {"city": HashIndex.build(sample_store, "city")}
    query = parse_sql("SELECT name FROM sample WHERE city = 'Beijing'")

    with_index = execute_query(sample_store, query, indices=indices)
    without_index = execute_query(sample_store, query)
    full_scan = execute_query(
        sample_store,
        query,
        indices=indices,
        force_full_scan=True,
    )

    assert {row["name"] for row in with_index.rows} == {"Alice", "David"}
    assert with_index.rows == without_index.rows == full_scan.rows
    assert with_index.used_index == "city"
    assert without_index.used_index is None
    assert full_scan.used_index is None


def test_index_with_and_condition(sample_store: RowStore):
    indices = {"city": HashIndex.build(sample_store, "city")}
    query = parse_sql(
        "SELECT name FROM sample WHERE city = 'Beijing' AND age > 30"
    )
    result = execute_query(sample_store, query, indices=indices)

    assert [row["name"] for row in result.rows] == ["David"]
    assert result.used_index == "city"


def test_or_condition_does_not_use_index(sample_store: RowStore):
    indices = {"city": HashIndex.build(sample_store, "city")}
    query = parse_sql(
        "SELECT name FROM sample WHERE city = 'Beijing' OR city = 'Chengdu'"
    )
    result = execute_query(sample_store, query, indices=indices)

    assert {row["name"] for row in result.rows} == {"Alice", "David", "Carol"}
    assert result.used_index is None


def test_save_and_load(tmp_path: Path):
    csv_path = tmp_path / "orders.csv"
    csv_path.write_text(
        "order_id,user_id,amount\n"
        "1,100,10\n"
        "2,200,20\n"
        "3,100,30\n",
        encoding="utf-8",
    )
    store = RowStore.from_csv(csv_path)
    index = HashIndex.build(store, "user_id")
    index_path = index.save(index_path_for(csv_path, "user_id"))

    reloaded = HashIndex.load(index_path, store)
    assert reloaded.lookup(100) == (0, 2)
    assert reloaded.lookup(200) == (1,)


def test_load_rejects_row_count_mismatch(tmp_path: Path):
    csv_path = tmp_path / "orders.csv"
    csv_path.write_text("order_id,user_id\n1,100\n", encoding="utf-8")
    store = RowStore.from_csv(csv_path)
    index = HashIndex.build(store, "user_id")
    index_path = index.save(index_path_for(csv_path, "user_id"))

    csv_path.write_text("order_id,user_id\n1,100\n2,200\n", encoding="utf-8")
    store2 = RowStore.from_csv(csv_path)
    with pytest.raises(IndexError, match="row count mismatch"):
        HashIndex.load(index_path, store2)


def test_load_or_build_creates_file(tmp_path: Path):
    csv_path = tmp_path / "items.csv"
    csv_path.write_text("id,tag\n1,a\n2,b\n", encoding="utf-8")
    store = RowStore.from_csv(csv_path)

    index = load_or_build_index(store, "tag")
    path = index_path_for(csv_path, "tag")
    assert path.is_file()
    assert index.lookup("a") == (0,)


def test_unknown_column_on_build(sample_store: RowStore):
    with pytest.raises(IndexError, match="UnknownColumn"):
        HashIndex.build(sample_store, "missing")
