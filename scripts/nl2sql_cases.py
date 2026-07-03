"""NL2SQL 测试用例批量运行（子模块 C · 报告素材）。"""

from __future__ import annotations

import argparse
import sys
import time
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from lite_db.executor import QueryError, QueryResult, execute_query, format_result
from lite_db.nl2sql import DEFAULT_MODEL, Nl2SqlError, nl_to_sql
from lite_db.parser import parse_sql
from lite_db.storage import RowStore


@dataclass(frozen=True, slots=True)
class NlCase:
    case_id: int
    question: str


DEFAULT_CASES: tuple[NlCase, ...] = (
    NlCase(1, "一共有多少条评分记录"),
    NlCase(2, "所有评分的总和和平均值是多少"),
    NlCase(3, "查询用户1的所有评分"),
    NlCase(4, "评分大于4的记录有哪些"),
    NlCase(5, "评分等于5的有多少条"),
    NlCase(6, "按评分从高到低排序"),
    NlCase(7, "用户1且评分不低于4的记录"),
    NlCase(8, "最高分和最低分分别是多少"),
    NlCase(9, "电影1的评分有哪些"),
    NlCase(10, "用户1或用户2的评分，按时间从早到晚排序"),
    NlCase(11, "评分不等于3的记录有多少条"),
    NlCase(12, "只查询用户5的userId和rating两列"),
    NlCase(13, "评分大于等于4且小于5的记录有哪些"),
    NlCase(14, "按电影ID升序排列，显示movieId和rating"),
    NlCase(15, "电影50有多少条评分"),
    NlCase(16, "评分小于1的记录有多少条"),
    NlCase(17, "用户1对电影1的评分是多少"),
    NlCase(18, "用户3一共有多少条评分"),
    NlCase(19, "评分大于4.5的记录按movieId排序"),
    NlCase(20, "用户1或用户2且评分等于5的有多少条"),
)


@dataclass(slots=True)
class CaseRun:
    case: NlCase
    status: str
    nl_ms: float
    exec_ms: float
    sql: str
    error: str | None = None
    row_count: int = 0
    result_text: str = ""


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="运行 NL2SQL 测试用例并输出报告")
    parser.add_argument("--data", default="data/ratings.csv", help="CSV 数据文件")
    parser.add_argument("--model", default=DEFAULT_MODEL, help="通义千问模型名")
    parser.add_argument(
        "--output",
        metavar="FILE",
        help="将完整报告写入文本文件（UTF-8）",
    )
    parser.add_argument(
        "--ids",
        metavar="N,N,...",
        help="只运行指定编号用例，如 1,3,5",
    )
    parser.add_argument(
        "--preview-rows",
        type=int,
        default=10,
        metavar="N",
        help="大结果集在报告中预览的前 N 行（默认 10；0 表示展示全部）",
    )
    return parser


def _parse_ids(raw: str | None) -> set[int] | None:
    if not raw:
        return None
    return {int(part.strip()) for part in raw.split(",") if part.strip()}


def _format_result_preview(result: QueryResult, preview_rows: int) -> str:
    total = len(result.rows)
    if total == 0:
        return "(empty result)"

    if preview_rows <= 0 or total <= preview_rows:
        body = format_result(result)
        return f"共 {total} 行\n{body}"

    preview = QueryResult(columns=result.columns, rows=result.rows[:preview_rows])
    body = format_result(preview)
    return f"共 {total} 行（以下预览前 {preview_rows} 行）\n{body}"


def _run_single_case(
    store: RowStore,
    case: NlCase,
    *,
    model: str,
    preview_rows: int,
) -> CaseRun:
    nl_started = time.perf_counter()
    try:
        conversion = nl_to_sql(store, case.question, model=model)
        nl_ms = (time.perf_counter() - nl_started) * 1000

        exec_started = time.perf_counter()
        query = parse_sql(conversion.sql)
        result = execute_query(store, query)
        exec_ms = (time.perf_counter() - exec_started) * 1000
        return CaseRun(
            case=case,
            status="OK",
            nl_ms=nl_ms,
            exec_ms=exec_ms,
            sql=conversion.sql,
            row_count=len(result.rows),
            result_text=_format_result_preview(result, preview_rows),
        )
    except (Nl2SqlError, QueryError, ValueError) as exc:
        nl_ms = (time.perf_counter() - nl_started) * 1000
        return CaseRun(
            case=case,
            status="FAIL",
            nl_ms=nl_ms,
            exec_ms=0.0,
            sql="",
            error=str(exc),
        )


def _render_report(
    store: RowStore,
    runs: list[CaseRun],
    *,
    model: str,
) -> str:
    ok_count = sum(1 for run in runs if run.status == "OK")
    lines: list[str] = []

    title = (
        f"lite-db NL2SQL 测试报告 | 表={store.table_name!r} | "
        f"rows={len(store):,} | model={model} | "
        f"用例 {len(runs)} 条 | 成功 {ok_count} 条"
    )
    lines.append("=" * 80)
    lines.append(title)
    lines.append("=" * 80)
    lines.append("")
    lines.append("【汇总表】")
    lines.append(
        f"{'#':<4}{'状态':<6}{'行数':>8}{'NL2SQL ms':>12}{'Exec ms':>12}  自然语言问句"
    )
    lines.append("-" * 80)
    for run in runs:
        rows = str(run.row_count) if run.status == "OK" else "-"
        lines.append(
            f"{run.case.case_id:<4}{run.status:<6}{rows:>8}"
            f"{run.nl_ms:>12.1f}{run.exec_ms:>12.1f}  {run.case.question}"
        )
    lines.append("-" * 80)
    lines.append("")

    for run in runs:
        lines.append("=" * 80)
        lines.append(f"用例 {run.case.case_id}: {run.case.question}")
        lines.append("=" * 80)
        lines.append(f"状态     : {run.status}")
        lines.append(f"NL2SQL   : {run.nl_ms:.1f} ms")
        lines.append(f"执行     : {run.exec_ms:.1f} ms")
        if run.status == "OK":
            lines.append(f"生成 SQL : {run.sql}")
            lines.append(f"结果行数 : {run.row_count}")
            lines.append("查询结果 :")
            lines.append(run.result_text)
        else:
            if run.sql:
                lines.append(f"生成 SQL : {run.sql}")
            lines.append(f"错误     : {run.error}")
        lines.append("")

    return "\n".join(lines)


def run_cases(
    store: RowStore,
    cases: tuple[NlCase, ...],
    *,
    model: str,
    preview_rows: int,
) -> list[CaseRun]:
    return [
        _run_single_case(store, case, model=model, preview_rows=preview_rows)
        for case in cases
    ]


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    csv_path = Path(args.data)
    if not csv_path.is_file():
        print(f"错误: 找不到 CSV 文件 {csv_path}", file=sys.stderr)
        return 1

    selected = _parse_ids(args.ids)
    cases = tuple(c for c in DEFAULT_CASES if selected is None or c.case_id in selected)
    if not cases:
        print("错误: 没有匹配的用例编号", file=sys.stderr)
        return 1

    store = RowStore.from_csv(csv_path)
    runs = run_cases(
        store,
        cases,
        model=args.model,
        preview_rows=args.preview_rows,
    )
    text = _render_report(store, runs, model=args.model)
    print(text)

    if args.output:
        out_path = Path(args.output)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(text + "\n", encoding="utf-8")
        print(f"已写入: {out_path}")

    failed = sum(1 for run in runs if run.status != "OK")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
