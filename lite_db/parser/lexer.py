"""SQL 词法分析。"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum, auto

from lite_db.parser.errors import SqlSyntaxError

KEYWORDS = frozenset(
    {
        "SELECT",
        "FROM",
        "WHERE",
        "AND",
        "OR",
        "ORDER",
        "BY",
        "ASC",
        "DESC",
        "COUNT",
        "SUM",
        "AVG",
        "MAX",
        "MIN",
        "NULL",
    }
)

IDENTIFIER_PATTERN = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")
NUMBER_PATTERN = re.compile(r"\d+(?:\.\d+)?")
OPERATORS = frozenset({"=", ">", "<", ">=", "<=", "!=", "<>"})


class TokenKind(Enum):
    KEYWORD = auto()
    IDENT = auto()
    STAR = auto()
    COMMA = auto()
    LPAREN = auto()
    RPAREN = auto()
    OPERATOR = auto()
    NUMBER = auto()
    STRING = auto()
    EOF = auto()


@dataclass(frozen=True, slots=True)
class Token:
    kind: TokenKind
    value: str
    pos: int


def tokenize(sql: str) -> list[Token]:
    tokens: list[Token] = []
    index = 0
    length = len(sql)

    while index < length:
        char = sql[index]

        if char.isspace():
            index += 1
            continue

        if char == "*":
            tokens.append(Token(TokenKind.STAR, "*", index))
            index += 1
            continue

        if char == ",":
            tokens.append(Token(TokenKind.COMMA, ",", index))
            index += 1
            continue

        if char == "(":
            tokens.append(Token(TokenKind.LPAREN, "(", index))
            index += 1
            continue

        if char == ")":
            tokens.append(Token(TokenKind.RPAREN, ")", index))
            index += 1
            continue

        if char == ";":
            index += 1
            continue

        if char == "'":
            start = index
            value, index = _read_string_literal(sql, index)
            tokens.append(Token(TokenKind.STRING, value, start))
            continue

        two_char = sql[index : index + 2]
        if two_char in OPERATORS:
            normalized = "!=" if two_char == "<>" else two_char
            tokens.append(Token(TokenKind.OPERATOR, normalized, index))
            index += 2
            continue

        if char in "=><":
            tokens.append(Token(TokenKind.OPERATOR, char, index))
            index += 1
            continue

        number_match = NUMBER_PATTERN.match(sql, index)
        if number_match:
            text = number_match.group(0)
            tokens.append(Token(TokenKind.NUMBER, text, index))
            index = number_match.end()
            continue

        ident_match = IDENTIFIER_PATTERN.match(sql, index)
        if ident_match:
            text = ident_match.group(0)
            upper = text.upper()
            if upper in KEYWORDS:
                tokens.append(Token(TokenKind.KEYWORD, upper, index))
            else:
                tokens.append(Token(TokenKind.IDENT, text, index))
            index = ident_match.end()
            continue

        raise SqlSyntaxError(f"unexpected character {char!r}", pos=index)

    tokens.append(Token(TokenKind.EOF, "", length))
    return tokens


def _read_string_literal(sql: str, index: int) -> tuple[str, int]:
    if sql[index] != "'":
        raise SqlSyntaxError("expected string literal", pos=index)

    index += 1
    chars: list[str] = []
    while index < len(sql):
        char = sql[index]
        if char == "'":
            if index + 1 < len(sql) and sql[index + 1] == "'":
                chars.append("'")
                index += 2
                continue
            return "".join(chars), index + 1
        chars.append(char)
        index += 1

    raise SqlSyntaxError("unterminated string literal", pos=index)
