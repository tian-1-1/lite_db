"""DashScope（通义千问）API 客户端。"""

from __future__ import annotations

import os
from http import HTTPStatus

from lite_db.nl2sql.errors import Nl2SqlApiError, Nl2SqlConfigError
from lite_db.nl2sql.prompt import DEFAULT_MODEL


def complete(
    messages: list[dict[str, str]],
    *,
    model: str = DEFAULT_MODEL,
    api_key: str | None = None,
) -> str:
    """调用通义千问 chat completion，返回 assistant 文本。"""
    try:
        from dashscope import Generation
    except ImportError as exc:
        raise Nl2SqlConfigError(
            "未安装 dashscope。请运行: uv sync --group nl2sql"
        ) from exc

    key = api_key or os.getenv("DASHSCOPE_API_KEY")
    if not key:
        raise Nl2SqlConfigError(
            "未设置 DASHSCOPE_API_KEY 环境变量。"
            "PowerShell: $env:DASHSCOPE_API_KEY = [Environment]::GetEnvironmentVariable('DASHSCOPE_API_KEY', 'User')"
        )

    response = Generation.call(
        model=model,
        messages=messages,
        result_format="message",
        api_key=key,
    )

    if response.status_code != HTTPStatus.OK:
        message = getattr(response, "message", None) or str(response)
        raise Nl2SqlApiError(
            f"DashScope 调用失败 (HTTP {response.status_code}): {message}"
        )

    try:
        return response.output.choices[0].message.content.strip()
    except (AttributeError, IndexError, TypeError) as exc:
        raise Nl2SqlApiError("DashScope 返回格式异常") from exc
