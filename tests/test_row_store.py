"""RowStore 与类型推断测试。"""

from pathlib import Path
from typing import Any

import pytest

from lite_db.storage import RowStore
from lite_db.types import ValueType


DATA_DIR = Path(__file__).resolve().parent.parent / "data"
SAMPLE_CSV = DATA_DIR / "sample.csv"


def _assert_value_matches_type(value: Any, column_type: ValueType) -> None:
    if value is None:
        return
    if column_type is ValueType.INTEGER:
        assert isinstance(value, int) and not isinstance(value, bool)
    elif column_type is ValueType.FLOAT:
        assert isinstance(value, (int, float)) and not isinstance(value, bool)
    elif column_type is ValueType.STRING:
        assert isinstance(value, str)


def _assert_store_schema_consistent(store: RowStore) -> None:
    assert store.table_name == store.path.stem
    assert len(store.column_names) == len(set(store.column_names))
    assert set(store.column_types.keys()) == set(store.column_names)

    for row in store.rows:
        assert set(row.keys()) == set(store.column_names)
        for name, value in row.items():
            _assert_value_matches_type(value, store.column_types[name])


def test_load_sample_csv_without_hardcoded_columns():
    """sample.csv 可随时改列/改行，只检查能否正确加载且结构自洽。"""
    if not SAMPLE_CSV.is_file():
        pytest.skip("data/sample.csv 不存在")

    store = RowStore.from_csv(SAMPLE_CSV)

    assert store.table_name == "sample"
    assert len(store.column_names) >= 1
    assert len(store) >= 1
    _assert_store_schema_consistent(store)


def test_every_row_matches_inferred_types(tmp_path: Path):
    csv_path = tmp_path / "typed.csv"
    csv_path.write_text(
        "id,name,amount\n"
        "1,Alice,10.5\n"
        "2,Bob,20\n",
        encoding="utf-8",
    )

    store = RowStore.from_csv(csv_path)
    _assert_store_schema_consistent(store)
    assert store.column_types["id"] is ValueType.INTEGER
    assert store.column_types["amount"] is ValueType.FLOAT


def test_null_and_integer_column(tmp_path: Path):
    csv_path = tmp_path / "nulls.csv"
    csv_path.write_text(
        "id,score,note\n"
        "1,100,ok\n"
        "2,,NULL\n"
        "3,NULL,NA\n",
        encoding="utf-8",
    )

    store = RowStore.from_csv(csv_path)

    assert store.column_types["id"] is ValueType.INTEGER
    assert store.column_types["score"] is ValueType.INTEGER
    assert store.get_row(1)["score"] is None
    assert store.get_row(2)["score"] is None


def test_mixed_numeric_column_becomes_float(tmp_path: Path):
    csv_path = tmp_path / "mixed.csv"
    csv_path.write_text("amount\n10\n3.5\n", encoding="utf-8")

    store = RowStore.from_csv(csv_path)
    assert store.column_types["amount"] is ValueType.FLOAT
    assert store.get_row(1)["amount"] == 3.5


def test_non_numeric_value_makes_string_column(tmp_path: Path):
    csv_path = tmp_path / "texty.csv"
    csv_path.write_text("value\n42\nabc\n", encoding="utf-8")

    store = RowStore.from_csv(csv_path)
    assert store.column_types["value"] is ValueType.STRING


def test_missing_file():
    with pytest.raises(FileNotFoundError):
        RowStore.from_csv(DATA_DIR / "missing.csv")


def test_invalid_row_width(tmp_path: Path):
    csv_path = tmp_path / "bad.csv"
    csv_path.write_text("a,b\n1,2,3\n", encoding="utf-8")

    with pytest.raises(ValueError, match="Column count mismatch"):
        RowStore.from_csv(csv_path)
