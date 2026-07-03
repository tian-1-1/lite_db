"""命令行交互入口。"""

from __future__ import annotations

import argparse
import sys
import time
from dataclasses import dataclass, field
from typing import Literal

from lite_db import __version__
from lite_db.executor import QueryError, execute_query, format_result
from lite_db.index import HashIndex, IndexError, index_path_for, load_or_build_index
from lite_db.nl2sql import DEFAULT_MODEL, Nl2SqlError, nl_to_sql
from lite_db.parser import SqlSyntaxError, parse_sql
from lite_db.storage import ColumnStore, ColumnStoreError, RowStore


StorageMode = Literal["row", "column"]


@dataclass
class TableSession:
    row_store: RowStore
    column_store: ColumnStore | None = None
    storage_mode: StorageMode = "row"
    indices: dict[str, HashIndex] = field(default_factory=dict)
    force_full_scan: bool = False

    @property
    def store(self) -> RowStore | ColumnStore:
        if self.storage_mode == "column":
            if self.column_store is None:
                raise ValueError("列式存储未加载，请使用 .build_colstore 或 --colstore")
            return self.column_store
        return self.row_store

    def build_index(self, column: str) -> HashIndex:
        index = HashIndex.build(self.row_store, column)
        path = index.save(index_path_for(self.row_store.path, column))
        self.indices[column] = index
        print(f"已建立索引: {index.describe()}")
        print(f"索引文件: {path}")
        return index

    def load_index(self, column: str) -> HashIndex:
        path = index_path_for(self.row_store.path, column)
        if path.is_file():
            index = HashIndex.load(path, self.row_store)
        else:
            index = load_or_build_index(self.row_store, column)
        self.indices[column] = index
        return index

    def build_colstore(self) -> ColumnStore:
        column_store = ColumnStore.build_from_csv(self.row_store.path)
        self.column_store = column_store
        print(f"已建立列存: {column_store.colstore_dir}")
        print(column_store.describe())
        return column_store

    def load_colstore(self) -> ColumnStore:
        column_store = ColumnStore.load_or_build(self.row_store.path)
        self.column_store = column_store
        return column_store


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="lite-db",
        description="轻量级 CSV 单表查询引擎（数据库原理课程项目）",
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"lite-db {__version__}",
    )
    parser.add_argument(
        "--data",
        metavar="CSV",
        help="加载 CSV 并进入交互模式（或与 --sql 配合执行单条查询）",
    )
    parser.add_argument(
        "--sql",
        metavar="QUERY",
        help="执行一条 SQL 查询",
    )
    parser.add_argument(
        "--index",
        metavar="COLUMN",
        action="append",
        dest="index_columns",
        help="启动时加载或构建指定列的哈希索引（可重复指定）",
    )
    parser.add_argument(
        "--no-index",
        action="store_true",
        help="强制全表扫描，忽略已加载的哈希索引",
    )
    parser.add_argument(
        "--colstore",
        action="store_true",
        help="启动时加载/构建列式存储，并以列存模式执行查询",
    )
    parser.add_argument(
        "--nl",
        metavar="QUESTION",
        help="自然语言查询（需配合 --data；调用通义千问转 SQL 后执行）",
    )
    parser.add_argument(
        "--nl-model",
        metavar="MODEL",
        default=DEFAULT_MODEL,
        help=f"NL2SQL 使用的通义千问模型（默认 {DEFAULT_MODEL}）",
    )
    return parser


def print_help(table_name: str) -> None:
    print(
        "\n".join(
            [
                "可用命令:",
                "  .help              显示帮助",
                "  .schema            显示当前表结构",
                "  .indexes           显示已加载的哈希索引",
                "  .build_index col   为指定列建立哈希索引并保存",
                "  .build_colstore    从 CSV 构建列式存储",
                "  .colstore          切换为列式存储模式",
                "  .rowstore          切换为行式存储模式（默认）",
                "  .scan              切换为全表扫描（忽略索引）",
                "  .use_index         切换为使用索引（默认）",
                "  .ask <问句>        自然语言查询（转 SQL 并执行）",
                "  .quit              退出（也可用 .exit）",
                "",
                "SQL 示例:",
                f"  SELECT * FROM {table_name}",
                f"  SELECT SUM(rating), AVG(rating) FROM {table_name}",
                f"  SELECT * FROM {table_name} WHERE userId = 1",
            ]
        )
    )


def run_query(session: TableSession, sql: str) -> str:
    started = time.perf_counter()
    query = parse_sql(sql)
    result = execute_query(
        session.store,
        query,
        indices=session.indices or None,
        force_full_scan=session.force_full_scan,
    )
    elapsed_ms = (time.perf_counter() - started) * 1000
    output = format_result(result)
    notes: list[str] = []
    if session.storage_mode == "column":
        notes.append("storage=column")
    if session.indices and not session.force_full_scan and result.used_index:
        notes.append(f"index={result.used_index!r}")
    elif session.indices and session.force_full_scan:
        notes.append("scan=full")
    if result.used_column_fast_path:
        notes.append("col-fast")
    note_text = f", {', '.join(notes)}" if notes else ""
    return (
        f"{output}\n({len(result.rows)} row(s) in {elapsed_ms:.2f} ms{note_text})"
    )


def run_nl_query(
    session: TableSession,
    question: str,
    *,
    model: str = DEFAULT_MODEL,
) -> str:
    """自然语言 → SQL → 执行，返回可打印文本。"""
    started = time.perf_counter()
    conversion = nl_to_sql(session.store, question, model=model)
    convert_ms = (time.perf_counter() - started) * 1000
    query_output = run_query(session, conversion.sql)
    return (
        f"生成 SQL: {conversion.sql}\n"
        f"(NL2SQL {convert_ms:.0f} ms, model={model})\n"
        f"{query_output}"
    )


def _prepare_session(
    csv_path: str,
    index_columns: list[str] | None,
    force_full_scan: bool,
    use_colstore: bool,
) -> TableSession:
    row_store = RowStore.from_csv(csv_path)
    session = TableSession(row_store=row_store, force_full_scan=force_full_scan)
    if use_colstore:
        session.load_colstore()
        session.storage_mode = "column"
    for column in index_columns or []:
        try:
            session.load_index(column)
        except IndexError as exc:
            raise ValueError(str(exc)) from exc
    return session


def run_repl(session: TableSession) -> int:
    store = session.store
    print(f"lite-db v{__version__} — 已加载表 {store.table_name!r} ({len(store)} rows)")
    print(f"当前存储: {'列式' if session.storage_mode == 'column' else '行式'}")
    if session.indices:
        columns = ", ".join(sorted(session.indices))
        print(f"已加载索引列: {columns}")
    if session.force_full_scan:
        print("当前模式: 全表扫描（--no-index）")
    print("输入 .help 查看帮助，.quit 退出。")

    while True:
        try:
            line = input("lite-db> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            return 0

        if not line:
            continue

        lowered = line.lower()
        if lowered in {".quit", ".exit"}:
            return 0
        if lowered == ".help":
            print_help(session.row_store.table_name)
            continue
        if lowered == ".schema":
            print(session.store.describe())
            continue
        if lowered == ".indexes":
            if not session.indices:
                print("(未加载索引)")
            else:
                for column in sorted(session.indices):
                    print(session.indices[column].describe())
            continue
        if lowered == ".scan":
            session.force_full_scan = True
            print("已切换为全表扫描模式。")
            continue
        if lowered == ".use_index":
            session.force_full_scan = False
            print("已切换为索引加速模式。")
            continue
        if lowered == ".colstore":
            try:
                if session.column_store is None:
                    session.load_colstore()
                session.storage_mode = "column"
                print("已切换为列式存储模式。")
            except (ColumnStoreError, FileNotFoundError, ValueError) as exc:
                print(f"错误: {exc}", file=sys.stderr)
            continue
        if lowered == ".rowstore":
            session.storage_mode = "row"
            print("已切换为行式存储模式。")
            continue
        if lowered == ".build_colstore":
            try:
                session.build_colstore()
            except (ColumnStoreError, ValueError) as exc:
                print(f"错误: {exc}", file=sys.stderr)
            continue
        if lowered.startswith(".build_index"):
            parts = line.split(maxsplit=1)
            if len(parts) != 2 or not parts[1].strip():
                print("用法: .build_index <column>", file=sys.stderr)
                continue
            try:
                session.build_index(parts[1].strip())
            except IndexError as exc:
                print(f"错误: {exc}", file=sys.stderr)
            continue
        if lowered.startswith(".ask"):
            parts = line.split(maxsplit=1)
            if len(parts) != 2 or not parts[1].strip():
                print("用法: .ask <自然语言问句>", file=sys.stderr)
                continue
            try:
                print(run_nl_query(session, parts[1].strip()))
            except Nl2SqlError as exc:
                print(f"错误: {exc}", file=sys.stderr)
            continue

        try:
            print(run_query(session, line))
        except (SqlSyntaxError, QueryError, ValueError) as exc:
            print(f"错误: {exc}", file=sys.stderr)


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    try:
        if args.data and args.nl and args.sql:
            raise ValueError("--nl 与 --sql 不能同时使用")

        if args.data and args.nl:
            session = _prepare_session(
                args.data,
                args.index_columns,
                args.no_index,
                args.colstore,
            )
            print(f"lite-db v{__version__}")
            print(run_nl_query(session, args.nl, model=args.nl_model))
            return 0

        if args.data and args.sql:
            session = _prepare_session(
                args.data,
                args.index_columns,
                args.no_index,
                args.colstore,
            )
            print(f"lite-db v{__version__}")
            print(run_query(session, args.sql))
            return 0

        if args.data:
            session = _prepare_session(
                args.data,
                args.index_columns,
                args.no_index,
                args.colstore,
            )
            return run_repl(session)

        if args.sql:
            query = parse_sql(args.sql)
            print(f"lite-db v{__version__}")
            print("SQL 解析结果:")
            print(f"  table: {query.table_name}")
            if query.selects_all:
                print("  columns: *")
            elif query.is_aggregate:
                print(f"  columns: {', '.join(query.output_labels())}")
            else:
                print(f"  columns: {', '.join(query.column_names())}")
            if query.where is not None:
                print(f"  where: {query.where}")
            if query.order_by:
                print(f"  order_by: {query.order_by}")
            print("\n提示: 加上 --data <path.csv> 可执行查询")
            return 0

        if args.nl:
            print(f"lite-db v{__version__}")
            print("提示: --nl 需配合 --data <path.csv> 使用")
            return 0

        print(f"lite-db v{__version__}")
        print('提示: uv run python -m lite_db --data data/sample.csv')
        return 0
    except (SqlSyntaxError, QueryError, FileNotFoundError, ValueError, Nl2SqlError) as exc:
        print(f"错误: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
