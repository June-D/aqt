"""pytest 必须在导入应用之前切到临时库，避免写入 data/trade.db。"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

_DB = Path(tempfile.mkdtemp(prefix="aqt-pytest-")) / "test.db"
os.environ["DATABASE_URL"] = f"sqlite:///{_DB}"
os.environ["APP_PASSWORD"] = ""
os.environ.setdefault("APP_USERNAME", "aqt")
