"""SQL Parser 测试。"""

import pytest

from lite_db.parser import (
    AndExpr,
    ColumnRef,
    ComparisonExpr,
    ComparisonOp,
    OrExpr,
    OrderItem,
    SortOrder,
    SqlSyntaxError,
    Star,
    parse_sql,
)


def test_select_star():
    query = parse_sql("SELECT * FROM sample")

    assert query.table_name == "sample"
    assert query.selects_all
    assert query.select_list == (Star(),)


def test_select_columns():
    query = parse_sql("SELECT name, age, salary FROM employees")

    assert query.table_name == "employees"
    assert not query.selects_all
    assert query.column_names() == ["name", "age", "salary"]
    assert query.select_list == (
        ColumnRef("name"),
        ColumnRef("age"),
        ColumnRef("salary"),
    )


def test_keywords_are_case_insensitive():
    query = parse_sql("select Name from Sample")
    assert query.table_name == "Sample"
    assert query.column_names() == ["Name"]


def test_allows_trailing_semicolon():
    query = parse_sql("SELECT * FROM sample;")
    assert query.table_name == "sample"


def test_missing_from():
    with pytest.raises(SqlSyntaxError, match="expected keyword FROM"):
        parse_sql("SELECT name")


def test_empty_select_list():
    with pytest.raises(SqlSyntaxError):
        parse_sql("SELECT FROM sample")


def test_invalid_character():
    with pytest.raises(SqlSyntaxError, match="unexpected character"):
        parse_sql("SELECT name FROM sample@")


def test_where_numeric_comparison():
    query = parse_sql("SELECT name FROM sample WHERE age >= 28")

    assert query.where == ComparisonExpr("age", ComparisonOp.GE, 28)


def test_where_string_comparison():
    query = parse_sql("SELECT name FROM sample WHERE city = 'Shanghai'")

    assert query.where == ComparisonExpr("city", ComparisonOp.EQ, "Shanghai")


def test_where_not_equal_operators():
    query1 = parse_sql("SELECT name FROM sample WHERE salary != 9800")
    query2 = parse_sql("SELECT name FROM sample WHERE salary <> 9800")

    assert query1.where == ComparisonExpr("salary", ComparisonOp.NE, 9800)
    assert query2.where == ComparisonExpr("salary", ComparisonOp.NE, 9800)


def test_string_escape():
    query = parse_sql("SELECT name FROM sample WHERE name = 'Al''ice'")
    assert isinstance(query.where, ComparisonExpr)
    assert query.where.value == "Al'ice"


def test_where_and_expression():
    query = parse_sql(
        "SELECT name FROM sample WHERE age > 25 AND city = 'Beijing'"
    )
    assert query.where == AndExpr(
        ComparisonExpr("age", ComparisonOp.GT, 25),
        ComparisonExpr("city", ComparisonOp.EQ, "Beijing"),
    )


def test_where_or_expression():
    query = parse_sql(
        "SELECT name FROM sample WHERE city = 'Beijing' OR city = 'Chengdu'"
    )
    assert query.where == OrExpr(
        ComparisonExpr("city", ComparisonOp.EQ, "Beijing"),
        ComparisonExpr("city", ComparisonOp.EQ, "Chengdu"),
    )


def test_and_binds_tighter_than_or():
    query = parse_sql(
        "SELECT name FROM sample WHERE age > 30 OR city = 'Chengdu' AND salary < 7000"
    )
    assert query.where == OrExpr(
        ComparisonExpr("age", ComparisonOp.GT, 30),
        AndExpr(
            ComparisonExpr("city", ComparisonOp.EQ, "Chengdu"),
            ComparisonExpr("salary", ComparisonOp.LT, 7000),
        ),
    )


def test_parentheses_override_precedence():
    query = parse_sql(
        "SELECT name FROM sample WHERE (city = 'Beijing' AND age > 25) OR salary > 12000"
    )
    assert query.where == OrExpr(
        AndExpr(
            ComparisonExpr("city", ComparisonOp.EQ, "Beijing"),
            ComparisonExpr("age", ComparisonOp.GT, 25),
        ),
        ComparisonExpr("salary", ComparisonOp.GT, 12000),
    )


def test_nested_parentheses():
    query = parse_sql("SELECT name FROM sample WHERE ((age > 25))")
    assert query.where == ComparisonExpr("age", ComparisonOp.GT, 25)


def test_unmatched_parenthesis():
    with pytest.raises(SqlSyntaxError, match="expected RPAREN"):
        parse_sql("SELECT name FROM sample WHERE (age > 25")


def test_unterminated_string():
    with pytest.raises(SqlSyntaxError, match="unterminated string"):
        parse_sql("SELECT name FROM sample WHERE city = 'Beijing")


def test_order_by_desc():
    query = parse_sql("SELECT name FROM sample ORDER BY salary DESC")
    assert query.order_by == (OrderItem("salary", SortOrder.DESC),)


def test_order_by_default_asc():
    query = parse_sql("SELECT name FROM sample ORDER BY age")
    assert query.order_by == (OrderItem("age", SortOrder.ASC),)


def test_order_by_multiple_columns():
    query = parse_sql("SELECT name FROM sample ORDER BY city ASC, salary DESC")
    assert query.order_by == (
        OrderItem("city", SortOrder.ASC),
        OrderItem("salary", SortOrder.DESC),
    )


def test_where_and_order_by():
    query = parse_sql(
        "SELECT name, salary FROM sample WHERE age > 25 ORDER BY salary DESC"
    )
    assert query.where == ComparisonExpr("age", ComparisonOp.GT, 25)
    assert query.order_by == (OrderItem("salary", SortOrder.DESC),)


def test_parse_count_star():
    query = parse_sql("SELECT COUNT(*) FROM sample")
    assert query.is_aggregate
    assert query.output_labels() == ["COUNT(*)"]


def test_parse_multiple_aggregates():
    query = parse_sql("SELECT COUNT(*), SUM(salary), AVG(age) FROM sample")
    assert query.output_labels() == ["COUNT(*)", "SUM(salary)", "AVG(age)"]


def test_parse_count_column():
    query = parse_sql("SELECT COUNT(name) FROM sample")
    assert query.select_list[0].column == "name"


def test_cannot_mix_aggregate_and_column():
    with pytest.raises(SqlSyntaxError, match="cannot mix aggregate"):
        parse_sql("SELECT name, COUNT(*) FROM sample")
