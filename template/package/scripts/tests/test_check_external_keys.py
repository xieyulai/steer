"""D2: check_external_keys 一次性检查 4 个外部 key。

隔离说明：dotenv_loader 在 import 时就把 ~/.auto-nn/.keys / ~/.env 等路径**冻结**
进 _GLOBAL_ENV_LOCATIONS（用 import 时的 Path.home()），运行时改 HOME 对它无效。
因此这里直接把 _GLOBAL_ENV_LOCATIONS patch 成空 tuple 来屏蔽真实机器凭证，
再用 patch.dict(clear=True) 隔离 os.environ —— 否则测试会因真 SERPER_KEY/GH_TOKEN
泄漏而“因错误理由通过”，clean HOME 上则失败。
"""
import os
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).parent.parent))

from lib.external.config import check_external_keys, KEY_VARS  # noqa: E402

# 屏蔽 import 时冻结的全局 .env / .keys 路径（改 HOME 无法覆盖，只能直接 patch）。
_GLOBAL_ENV_PATCH = "lib.external.dotenv_loader._GLOBAL_ENV_LOCATIONS"


def test_check_external_keys_all_set():
    """D2: 4 个 key 全配 → dict 全 True。"""
    env = {
        "SERPER_API_KEY": "x",
        "OPENAI_API_KEY": "y",
        "GITHUB_TOKEN": "z",
        "ANTHROPIC_API_KEY": "w",
    }
    with patch(_GLOBAL_ENV_PATCH, ()), patch.dict(os.environ, env, clear=True):
        result = check_external_keys(repo_root=Path("/tmp/nonexistent_for_test"))
    assert result == {k: True for k in KEY_VARS}


def test_check_external_keys_all_unset():
    """D2: 全 unset → dict 全 False,不抛异常。"""
    with tempfile.TemporaryDirectory() as tmp:
        # 无全局 .env、os.environ 全清、repo_root 无 .env → 4 个 key 全缺。
        with patch(_GLOBAL_ENV_PATCH, ()), patch.dict(os.environ, {}, clear=True):
            result = check_external_keys(repo_root=Path(tmp))
    assert result == {k: False for k in KEY_VARS}, f"expected all False, got {result}"


def test_dotenv_loading_via_repo_root():
    """D2: 临时 .env 文件含 SERPER_API_KEY → 走 dotenv_loader 找到 → True。
    OPENAI_API_KEY 未在 .env 也未在 env → False。
    """
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        (tmp_path / ".env").write_text("SERPER_API_KEY=from_dotenv\n", encoding="utf-8")
        # os.environ 全清且不预置 key → tmp/.env 才能把 SERPER_API_KEY 填进来。
        with patch(_GLOBAL_ENV_PATCH, ()), patch.dict(os.environ, {}, clear=True):
            result = check_external_keys(repo_root=tmp_path)
    assert result["SERPER_API_KEY"] is True, f"expected SERPER_API_KEY True, got {result}"
    assert result["OPENAI_API_KEY"] is False, f"expected OPENAI_API_KEY False, got {result}"
