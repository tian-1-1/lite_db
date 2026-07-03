"""NL2SQL Prompt 构建。"""

from __future__ import annotations

from lite_db.storage.table_store import TableStore

DEFAULT_MODEL = "qwen-plus"

_SUPPORTED_SQL_RULES = """\
支持的 SQL 能力（本项目 SQL 子集）：
- SELECT 投影：* 或列名列表
- WHERE：= > < >= <= !=，以及 AND / OR、括号
- ORDER BY：ASC / DESC，可多列
- 聚合：COUNT(*)、COUNT(col)、SUM、AVG、MAX、MIN（作用于全表或 WHERE 过滤后的结果）
- 单表 FROM，表名必须与当前表完全一致

禁止使用的语法（不要生成）：
- JOIN、GROUP BY、HAVING、DISTINCT、LIMIT、OFFSET
- LIKE、IN、BETWEEN、IS NULL、NOT
- 子查询、UNION、表达式列、AS 别名
"""


def build_system_prompt(store: TableStore) -> str:
    column_lines = "\n".join(
        f"  - {name}: {store.column_types[name].value}"
        for name in store.column_names
    )
    return (
        "你是 lite-db 的 SQL 生成助手。根据用户的中文问题，生成一条可执行的 SQL。\n"
        f"当前数据库只有一张表 `{store.table_name}`，共 {len(store)} 行，列如下：\n"
        f"{column_lines}\n\n"
        f"{_SUPPORTED_SQL_RULES}\n"
        "输出要求：\n"
        "- 只输出一条 SQL 语句，不要解释、不要 Markdown 标题\n"
        "- 列名、表名必须与上面 schema 完全一致（区分大小写）\n"
        "- 字符串字面量使用单引号\n"
    )


def build_messages(store: TableStore, question: str) -> list[dict[str, str]]:
    return [
        {"role": "system", "content": build_system_prompt(store)},
        {"role": "user", "content": question.strip()},
    ]
