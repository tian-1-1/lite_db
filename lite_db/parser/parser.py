"""SQL 语法分析。"""

from __future__ import annotations

from lite_db.parser.ast import (
    AggregateExpr,
    AggregateFunc,
    AndExpr,
    BoolExpr,
    ColumnRef,
    ComparisonExpr,
    ComparisonOp,
    LiteralValue,
    OrderItem,
    OrExpr,
    SelectItem,
    SelectQuery,
    SortOrder,
    Star,
)
from lite_db.parser.errors import SqlSyntaxError
from lite_db.parser.lexer import Token, TokenKind, tokenize

_AGGREGATE_KEYWORDS = frozenset(func.value for func in AggregateFunc)


class SqlParser:
    def __init__(self, sql: str) -> None:
        self._tokens = tokenize(sql)
        self._index = 0

    def parse(self) -> SelectQuery:
        self._expect_keyword("SELECT")
        select_list = self._parse_select_list()
        self._expect_keyword("FROM")
        table_name = self._expect_identifier()
        where = self._parse_where()
        order_by = self._parse_order_by()
        self._expect(TokenKind.EOF)
        return SelectQuery(
            select_list=select_list,
            table_name=table_name,
            where=where,
            order_by=order_by,
        )

    def _parse_select_list(self) -> tuple[SelectItem, ...]:
        items: list[SelectItem] = []
        while True:
            items.append(self._parse_select_item())
            if not self._match(TokenKind.COMMA):
                break
        if not items:
            raise SqlSyntaxError("SELECT list cannot be empty", pos=self._peek().pos)
        if len(items) == 1 and isinstance(items[0], Star):
            return (Star(),)
        if any(isinstance(item, Star) for item in items):
            raise SqlSyntaxError(
                "cannot use * together with other select items",
                pos=self._peek().pos,
            )

        has_aggregate = any(isinstance(item, AggregateExpr) for item in items)
        has_column = any(isinstance(item, ColumnRef) for item in items)
        if has_aggregate and has_column:
            raise SqlSyntaxError(
                "cannot mix aggregate functions with plain columns in SELECT list",
                pos=self._peek().pos,
            )
        return tuple(items)

    def _parse_select_item(self) -> SelectItem:
        if self._check_aggregate_keyword():
            return self._parse_aggregate()
        if self._check(TokenKind.STAR):
            self._advance()
            return Star()
        return ColumnRef(self._expect_identifier())

    def _parse_aggregate(self) -> AggregateExpr:
        token = self._peek()
        func = AggregateFunc(token.value)
        self._advance()
        self._expect(TokenKind.LPAREN)

        column: str | None
        if func is AggregateFunc.COUNT and self._check(TokenKind.STAR):
            self._advance()
            column = None
        else:
            column = self._expect_identifier()

        self._expect(TokenKind.RPAREN)
        return AggregateExpr(func=func, column=column)

    def _parse_where(self) -> BoolExpr | None:
        if not self._check_keyword("WHERE"):
            return None
        self._advance()
        return self._parse_or_expr()

    def _parse_order_by(self) -> tuple[OrderItem, ...]:
        if not self._check_keyword("ORDER"):
            return ()
        self._advance()
        self._expect_keyword("BY")

        items: list[OrderItem] = []
        while True:
            column = self._expect_order_by_column()
            order = SortOrder.ASC
            if self._check_keyword("ASC"):
                self._advance()
            elif self._check_keyword("DESC"):
                self._advance()
                order = SortOrder.DESC
            items.append(OrderItem(column=column, order=order))
            if not self._match(TokenKind.COMMA):
                break
        return tuple(items)

    def _expect_order_by_column(self) -> str:
        token = self._peek()
        if token.kind is TokenKind.IDENT:
            return self._advance().value
        if token.kind is TokenKind.KEYWORD and token.value in _AGGREGATE_KEYWORDS:
            aggregate = self._parse_aggregate()
            return aggregate.output_name()
        raise SqlSyntaxError(
            f"expected order by column or aggregate, got {token.value!r}",
            pos=token.pos,
        )

    def _parse_or_expr(self) -> BoolExpr:
        expr = self._parse_and_expr()
        while self._check_keyword("OR"):
            self._advance()
            expr = OrExpr(left=expr, right=self._parse_and_expr())
        return expr

    def _parse_and_expr(self) -> BoolExpr:
        expr = self._parse_primary_expr()
        while self._check_keyword("AND"):
            self._advance()
            expr = AndExpr(left=expr, right=self._parse_primary_expr())
        return expr

    def _parse_primary_expr(self) -> BoolExpr:
        if self._match(TokenKind.LPAREN):
            expr = self._parse_or_expr()
            self._expect(TokenKind.RPAREN)
            return expr
        return self._parse_comparison()

    def _parse_comparison(self) -> ComparisonExpr:
        column = self._expect_identifier()
        operator = self._expect_operator()
        value = self._parse_literal()
        return ComparisonExpr(column=column, op=operator, value=value)

    def _parse_literal(self) -> LiteralValue:
        token = self._peek()
        if token.kind is TokenKind.KEYWORD and token.value == "NULL":
            self._advance()
            return None
        if token.kind is TokenKind.NUMBER:
            self._advance()
            return _parse_number(token.value)
        if token.kind is TokenKind.STRING:
            self._advance()
            return token.value
        raise SqlSyntaxError(
            f"expected literal, got {token.value!r}",
            pos=token.pos,
        )

    def _expect_operator(self) -> ComparisonOp:
        token = self._peek()
        if token.kind is TokenKind.OPERATOR:
            self._advance()
            try:
                return ComparisonOp(token.value)
            except ValueError as exc:
                raise SqlSyntaxError(
                    f"unsupported operator {token.value!r}",
                    pos=token.pos,
                ) from exc
        raise SqlSyntaxError(f"expected operator, got {token.value!r}", pos=token.pos)

    def _expect_keyword(self, keyword: str) -> Token:
        token = self._peek()
        if token.kind is TokenKind.KEYWORD and token.value == keyword:
            return self._advance()
        if token.kind is TokenKind.KEYWORD:
            message = f"expected {keyword}, got {token.value}"
        else:
            message = f"expected keyword {keyword}, got {token.value!r}"
        raise SqlSyntaxError(message, pos=token.pos)

    def _expect_identifier(self) -> str:
        token = self._peek()
        if token.kind is TokenKind.IDENT:
            return self._advance().value
        raise SqlSyntaxError(f"expected identifier, got {token.value!r}", pos=token.pos)

    def _expect(self, kind: TokenKind) -> Token:
        token = self._peek()
        if token.kind is kind:
            return self._advance()
        raise SqlSyntaxError(f"expected {kind.name}, got {token.value!r}", pos=token.pos)

    def _match(self, kind: TokenKind) -> bool:
        if self._peek().kind is kind:
            self._advance()
            return True
        return False

    def _check(self, kind: TokenKind) -> bool:
        return self._peek().kind is kind

    def _check_keyword(self, keyword: str) -> bool:
        token = self._peek()
        return token.kind is TokenKind.KEYWORD and token.value == keyword

    def _check_aggregate_keyword(self) -> bool:
        token = self._peek()
        return token.kind is TokenKind.KEYWORD and token.value in _AGGREGATE_KEYWORDS

    def _peek(self) -> Token:
        return self._tokens[self._index]

    def _advance(self) -> Token:
        token = self._tokens[self._index]
        self._index += 1
        return token


def _parse_number(text: str) -> int | float:
    if "." in text:
        return float(text)
    return int(text)


def parse_sql(sql: str) -> SelectQuery:
    """解析 SQL 字符串为 SelectQuery AST。"""
    return SqlParser(sql).parse()
