#!/usr/bin/env python3
from __future__ import annotations

import sys
from pathlib import Path


TOOL_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = TOOL_ROOT / "src"

if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from ai_consult.legacy import main


if __name__ == "__main__":
    raise SystemExit(main(target="chatgpt"))
