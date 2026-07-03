"""等值查询：有索引 vs 无索引 性能对比。"""

from __future__ import annotations

import argparse
import statistics
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from lite_db.executor import execute_query
from lite_db.index import HashIndex, load_or_build_index
from lite_db.parser import parse_sql
from lite_db.storage import RowStore


def _percentile(values: list[float], p: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    rank = (len(ordered) - 1) * p
    low = int(rank)
    high = min(low + 1, len(ordered) - 1)
    weight = rank - low
    return ordered[low] * (1 - weight) + ordered[high] * weight


def _run_timed(
    store: RowStore,
    sql: str,
    *,
    indices: dict[str, HashIndex] | None,
    force_full_scan: bool,
    iterations: int,
    warmup: int,
) -> tuple[list[float], int]:
    query = parse_sql(sql)
    for _ in range(warmup):
        execute_query(
            store,
            query,
            indices=indices,
            force_full_scan=force_full_scan,
        )

    samples: list[float] = []
    row_count = 0
    for _ in range(iterations):
        started = time.perf_counter()
        result = execute_query(
            store,
            query,
            indices=indices,
            force_full_scan=force_full_scan,
        )
        elapsed_ms = (time.perf_counter() - started) * 1000
        samples.append(elapsed_ms)
        row_count = len(result.rows)
    return samples, row_count


def _summarize(samples: list[float]) -> dict[str, float]:
    return {
        "mean_ms": statistics.mean(samples),
        "median_ms": statistics.median(samples),
        "p95_ms": _percentile(samples, 0.95),
        "min_ms": min(samples),
        "max_ms": max(samples),
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="对比等值查询在有/无哈希索引下的耗时",
    )
    parser.add_argument(
        "--data",
        default="data/ratings.csv",
        help="CSV 数据路径（默认 data/ratings.csv）",
    )
    parser.add_argument(
        "--column",
        default="userId",
        help="建立哈希索引的列名（默认 userId）",
    )
    parser.add_argument(
        "--value",
        default="1",
        help="等值查询的字面量（默认 1）",
    )
    parser.add_argument(
        "--iterations",
        type=int,
        default=100,
        help="计时重复次数（默认 100）",
    )
    parser.add_argument(
        "--warmup",
        type=int,
        default=10,
        help="预热次数，不计入统计（默认 10）",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    csv_path = Path(args.data)
    if not csv_path.is_file():
        print(f"错误: 找不到 CSV 文件 {csv_path}", file=sys.stderr)
        return 1

    store = RowStore.from_csv(csv_path)
    table = store.table_name
    column = args.column
    literal = args.value

    if column not in store.column_names:
        print(f"错误: 列 {column!r} 不存在，可选: {store.column_names}", file=sys.stderr)
        return 1

    col_type = store.column_types[column]
    if col_type.value in {"INTEGER", "FLOAT"}:
        query_value: int | float | str = float(literal) if "." in literal else int(literal)
        sql = f"SELECT * FROM {table} WHERE {column} = {query_value}"
    else:
        query_value = literal
        sql = f"SELECT * FROM {table} WHERE {column} = '{query_value}'"

    print("=" * 60)
    print("lite-db 哈希索引性能对比")
    print("=" * 60)
    print(f"数据文件 : {csv_path}")
    print(f"表行数   : {len(store):,}")
    print(f"查询 SQL : {sql}")

    build_started = time.perf_counter()
    index = load_or_build_index(store, column)
    build_ms = (time.perf_counter() - build_started) * 1000
    indices = {column: index}

    print(f"索引列   : {column}（distinct keys = {index.distinct_key_count():,}）")
    print(f"索引构建 : {build_ms:.2f} ms")
    print(f"迭代次数 : {args.iterations}（预热 {args.warmup} 次）")
    print("-" * 60)

    indexed_samples, row_count = _run_timed(
        store,
        sql,
        indices=indices,
        force_full_scan=False,
        iterations=args.iterations,
        warmup=args.warmup,
    )
    scan_samples, _ = _run_timed(
        store,
        sql,
        indices=indices,
        force_full_scan=True,
        iterations=args.iterations,
        warmup=args.warmup,
    )

    indexed = _summarize(indexed_samples)
    scanned = _summarize(scan_samples)
    speedup = scanned["mean_ms"] / indexed["mean_ms"] if indexed["mean_ms"] > 0 else 0

    print(f"命中行数 : {row_count}")
    print()
    print(f"{'指标':<12} {'有索引 (ms)':>14} {'全表扫描 (ms)':>16}")
    print("-" * 44)
    for key, label in [
        ("mean_ms", "均值"),
        ("median_ms", "中位数"),
        ("p95_ms", "P95"),
        ("min_ms", "最小"),
        ("max_ms", "最大"),
    ]:
        print(f"{label:<12} {indexed[key]:>14.3f} {scanned[key]:>16.3f}")
    print("-" * 44)
    print(f"加速比 (全表扫描均值 / 有索引均值): {speedup:.2f}x")
    print()
    print("报告建议：")
    print("  1. 记录上表数据，说明测试环境（CPU、Python 版本、行数）")
    print("  2. 解释：等值查询走索引 O(1) 定位 + 取行，全表扫描 O(n) 逐行比较")
    print("  3. 可换不同 userId 或增大 iterations 复测")
    return 0


if __name__ == "__main__":
    sys.exit(main())
