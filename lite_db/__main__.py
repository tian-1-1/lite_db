"""允许通过 ``python -m lite_db`` 启动 CLI。"""

from lite_db.cli import main

if __name__ == "__main__":
    raise SystemExit(main())
