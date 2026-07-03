"""NL2SQL 相关异常。"""


class Nl2SqlError(Exception):
    """自然语言转 SQL 流程中的错误基类。"""


class Nl2SqlConfigError(Nl2SqlError):
    """缺少 API Key、未安装 dashscope 等配置问题。"""


class Nl2SqlApiError(Nl2SqlError):
    """调用大模型 API 失败。"""


class Nl2SqlValidationError(Nl2SqlError):
    """模型生成的 SQL 未通过校验。"""


class Nl2SqlExtractError(Nl2SqlError):
    """无法从模型回复中提取 SQL。"""
