from __future__ import annotations

from pathlib import Path


def main() -> int:
    # 先保留一个轻量入口，方便未来继续把 Toolkit 命令体系扩展下去。
    root = Path(__file__).resolve().parent
    print(f"Linux Toolkit ready at: {root}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
