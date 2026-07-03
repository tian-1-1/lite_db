"""自然语言转 SQL（子模块 C）。"""

from lite_db.nl2sql.errors import (
    Nl2SqlApiError,
    Nl2SqlConfigError,
    Nl2SqlError,
    Nl2SqlExtractError,
    Nl2SqlValidationError,
)
from lite_db.nl2sql.pipeline import Nl2SqlResult, nl_to_sql
from lite_db.nl2sql.prompt import DEFAULT_MODEL, build_messages, build_system_prompt

__all__ = [
    "DEFAULT_MODEL",
    "Nl2SqlApiError",
    "Nl2SqlConfigError",
    "Nl2SqlError",
    "Nl2SqlExtractError",
    "Nl2SqlResult",
    "Nl2SqlValidationError",
    "build_messages",
    "build_system_prompt",
    "nl_to_sql",
]
