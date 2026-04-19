"""CLI entrypoint.  Run as:  python -m funding_rate_monitor"""

from __future__ import annotations

import sys

from funding_rate_monitor.config import Config
from funding_rate_monitor.runner import run


def main() -> None:
    cfg = Config()
    run(cfg)
    sys.exit(0)


if __name__ == "__main__":
    main()
