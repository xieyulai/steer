"""Physical 契约常量占位。"""
from __future__ import annotations

import os
from pathlib import Path

# ── 数据目录配置 ─────────────────────────────────────────────────
# 优先级：NN_DATA_DIR 环境变量 > DEFAULT_DATA_DIR > data/
# 数据量小（<1GB）：拷贝到 data/ 目录
# 数据量大（>=1GB）：软链接指向原始数据路径
#   ln -s /path/to/original/data data/dataset_name
DEFAULT_DATA_DIR = os.environ.get("NN_DATA_DIR", str(Path(__file__).resolve().parent.parent / "data"))
