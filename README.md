# lite-db

轻量级 CSV 单表查询引擎 — 数据库原理课程项目（**题目二：轻量级数据库引擎**）

**作者**：李甜甜 · **学号**：42411086 · **学校**：西南财经大学

## 功能概览

| 子模块 | 状态 | 说明 |
|--------|------|------|
| A · 查询引擎 | ✅ 已完成 | 过滤、聚合、排序、投影、CLI |
| A · 哈希索引 | ✅ 已完成 | 单列等值索引 + 持久化；`benchmark.py` 性能对比 |
| B · 列式存储 | ✅ 已完成 | 列存读写 + `benchmark_storage.py` 行/列对比 |
| C · NL2SQL | ✅ 已完成 | 通义千问 DashScope；`.ask` / `--nl`；20 条用例脚本 |

## 环境要求

- Python **3.11+**
- [uv](https://docs.astral.sh/uv/) 包管理器
- NL2SQL 另需配置环境变量 `DASHSCOPE_API_KEY`（勿提交到 Git）

## 快速开始

```bash
# 克隆仓库后进入本项目根目录（含 pyproject.toml 的目录）

# 安装依赖（含 editable 安装）
uv sync --dev

# 自然语言查询（子模块 C）还需 dashscope
uv sync --dev --group nl2sql

# 配置通义千问 API Key（PowerShell 永久设置示例）
# [System.Environment]::SetEnvironmentVariable("DASHSCOPE_API_KEY", "sk-...", "User")

# 交互式 CLI（加载 CSV 后输入 SQL）
uv run python -m lite_db --data data/sample.csv

# 单条 SQL 非交互执行
uv run python -m lite_db --data data/sample.csv --sql "SELECT name, salary FROM sample ORDER BY salary DESC"

# 加载/构建 city 列哈希索引后执行等值查询
uv run python -m lite_db --data data/sample.csv --index city --sql "SELECT * FROM sample WHERE city = 'Beijing'"

# 哈希索引性能对比（子模块 A）
uv run python scripts/benchmark.py --data data/ratings.csv --column userId --value 1

# 列存对比（子模块 B）
uv run python scripts/benchmark_storage.py --data data/ratings.csv --iterations 50
uv run python -m lite_db --data data/ratings.csv --colstore --sql "SELECT SUM(rating), AVG(rating) FROM ratings"

# 自然语言查询（子模块 C）
uv run python -m lite_db --data data/ratings.csv --nl "一共有多少条评分记录"
uv run python -m lite_db --data data/ratings.csv
# lite-db> .ask 用户1的评分有哪些

# 20 条 NL2SQL 用例批量运行（需网络 + DASHSCOPE_API_KEY）
uv run python scripts/nl2sql_cases.py --data data/ratings.csv --output nl2sql_cases.txt

# 运行单元测试
uv run pytest
```

## 目录结构

```
.
├── lite_db/           # 核心代码
│   ├── parser/        # SQL 解析
│   ├── executor/      # 查询执行
│   ├── storage/       # 行存 / 列存
│   ├── index/         # 哈希索引
│   ├── nl2sql/        # 自然语言查询
│   └── cli.py         # 命令行入口
├── data/              # 样例与实验数据（ratings.csv 约 10 万行）
├── scripts/           # 基准测试与 NL2SQL 批量脚本
└── tests/             # 单元测试
```

## 数据说明

| 文件 | 说明 |
|------|------|
| `data/ratings.csv` | MovieLens 评分表，100 836 行，主实验数据 |
| `data/sample.csv` | 5 行小表，快速演示与调试 |
| `data/*.hidx` | 哈希索引文件（首次 `--index` 或 benchmark 时自动生成，可删后重建） |
| `data/*.colstore/` | 列存目录（首次 `--colstore` 或 benchmark 时自动生成，可删后重建） |

## SQL 示例

```sql
-- 条件过滤 + 投影（sample 表）
SELECT name, salary FROM sample WHERE age > 25 AND city = 'Beijing'

-- 聚合（ratings 表）
SELECT COUNT(*), AVG(rating) FROM ratings

-- 排序
SELECT * FROM sample ORDER BY salary DESC

-- 等值查询（配合 --index userId 可走哈希索引）
SELECT * FROM ratings WHERE userId = 1
```

## 许可证

课程作业项目，仅供学习使用。
