"""行式存储 vs 列式存储性能对比。"""

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
from lite_db.parser import parse_sql
from lite_db.storage import ColumnStore, RowStore


def _percentile(values: list[float], p: float) -> float:
    ordered = sorted(values)
    rank = (len(ordered) - 1) * p
    low = int(rank)
    high = min(low + 1, len(ordered) - 1)
    weight = rank - low
    return ordered[low] * (1 - weight) + ordered[high] * weight


def _summarize(samples: list[float]) -> dict[str, float]:
    return {
        "mean_ms": statistics.mean(samples),
        "median_ms": statistics.median(samples),
        "p95_ms": _percentile(samples, 0.95),
    }


def _bench_query(
    store: RowStore | ColumnStore,
    sql: str,
    *,
    iterations: int,
    warmup: int,
    clear_column_cache: bool,
) -> list[float]:
    query = parse_sql(sql)
    for _ in range(warmup):
        if isinstance(store, ColumnStore) and clear_column_cache:
            store.clear_cache()
        execute_query(store, query)

    samples: list[float] = []
    for _ in range(iterations):
        if isinstance(store, ColumnStore) and clear_column_cache:
            store.clear_cache()
        started = time.perf_counter()
        execute_query(store, query)
        samples.append((time.perf_counter() - started) * 1000)
    return samples


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="对比行式存储与列式存储的查询耗时",
    )
    parser.add_argument("--data", default="data/ratings.csv")
    parser.add_argument(
        "--scenario",
        choices=["aggregate", "fullscan", "both"],
        default="both",
        help="aggregate=SUM/AVG；fullscan=SELECT *；both=两者都测",
    )
    parser.add_argument("--iterations", type=int, default=50)
    parser.add_argument("--warmup", type=int, default=5)
    parser.add_argument(
        "--cold-column-cache",
        action="store_true",
        help="列存每次迭代前清空列缓存（模拟重复冷读单列/全列）",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    csv_path = Path(args.data)
    if not csv_path.is_file():
        print(f"错误: 找不到 CSV 文件 {csv_path}", file=sys.stderr)
        return 1

    row_store = RowStore.from_csv(csv_path)
    build_started = time.perf_counter()
    column_store = ColumnStore.load_or_build(csv_path)
    build_ms = (time.perf_counter() - build_started) * 1000
    table = row_store.table_name

    scenarios: list[tuple[str, str]] = []
    if args.scenario in {"aggregate", "both"}:
        scenarios.append(
            ("聚合 SUM/AVG", f"SELECT SUM(rating), AVG(rating) FROM {table}")
        )
    if args.scenario in {"fullscan", "both"}:
        scenarios.append(("全行读取 SELECT *", f"SELECT * FROM {table}"))

    print("=" * 60)
    print("lite-db 行存 vs 列存性能对比")
    print("=" * 60)
    print(f"数据文件 : {csv_path}")
    print(f"表行数   : {len(row_store):,}")
    print(f"列存目录 : {column_store.colstore_dir}")
    print(f"列存构建 : {build_ms:.2f} ms")
    print(f"迭代次数 : {args.iterations}（预热 {args.warmup} 次）")
    if args.cold_column_cache:
        print("列存策略 : 每次迭代前 clear_cache()")
    print("-" * 60)

    for label, sql in scenarios:
        row_samples = _bench_query(
            row_store,
            sql,
            iterations=args.iterations,
            warmup=args.warmup,
            clear_column_cache=False,
        )
        col_samples = _bench_query(
            column_store,
            sql,
            iterations=args.iterations,
            warmup=args.warmup,
            clear_column_cache=args.cold_column_cache,
        )
        row_stats = _summarize(row_samples)
        col_stats = _summarize(col_samples)
        speedup = row_stats["mean_ms"] / col_stats["mean_ms"] if col_stats["mean_ms"] else 0

        print(f"场景     : {label}")
        print(f"SQL      : {sql}")
        print(f"{'指标':<10} {'行存 (ms)':>12} {'列存 (ms)':>12}")
        print("-" * 38)
        for key, name in [("mean_ms", "均值"), ("median_ms", "中位数"), ("p95_ms", "P95")]:
            print(f"{name:<10} {row_stats[key]:>12.3f} {col_stats[key]:>12.3f}")
        print(f"行存/列存均值比: {speedup:.2f}x（>1 表示列存更快）")
        print("-" * 60)

    print("报告提示：聚合场景预期列存更快；SELECT * 预期行存更快。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
