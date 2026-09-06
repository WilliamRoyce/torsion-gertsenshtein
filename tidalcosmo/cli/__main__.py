"""Allow ``python -m tidalcosmo.cli`` invocation."""

from __future__ import annotations

import sys

from tidalcosmo.cli import main

if __name__ == "__main__":
    sys.exit(main())
