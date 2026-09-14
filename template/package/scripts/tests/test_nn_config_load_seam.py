"""跨 seam：纯 v4 nn-config 经 lib 回填后，Run Context 与 KEEP 口径一致。"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest
import yaml

SCRIPTS = Path(__file__).resolve().parents[1]
TEMPLATE_PKG = SCRIPTS.parent


def _load_brc():
    path = SCRIPTS / "build-run-context.py"
    spec = importlib.util.spec_from_file_location("_brc_nn_config_seam", path)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


def test_v4_only_injection_off_reaches_run_context_and_keep_preset(tmp_path):
    """只有 context.injection: off、无 agent.* / keep → 注入 off 且 keep 来自 preset。"""
    (tmp_path / "nn-config.yaml").write_text(
        yaml.dump(
            {
                "exploration_mode": "optimize",
                "context": {"injection": "off"},
            },
            allow_unicode=True,
        ),
        encoding="utf-8",
    )

    if str(SCRIPTS) not in sys.path:
        sys.path.insert(0, str(SCRIPTS))
    if str(TEMPLATE_PKG) not in sys.path:
        sys.path.insert(0, str(TEMPLATE_PKG))

    from lib.nn_config import load_nn_config

    full = load_nn_config(tmp_path)
    assert full["context"]["injection"] == "off"
    assert isinstance(full.get("keep"), dict) and full["keep"]

    brc = _load_brc()
    assert brc.run_context_config(tmp_path) == "off"

    import experiment as exp_mod

    keep_cfg = exp_mod._load_nn_config(tmp_path).get("keep") or {}
    assert keep_cfg, "KEEP 应拿到 preset 合并后的 keep，不能再是裸读空 dict"


def test_load_nn_config_malformed_yaml_raises(tmp_path):
    (tmp_path / "nn-config.yaml").write_text(":\n  - broken", encoding="utf-8")
    if str(SCRIPTS) not in sys.path:
        sys.path.insert(0, str(SCRIPTS))
    from lib.nn_config import load_nn_config

    with pytest.raises(RuntimeError, match="parse error"):
        load_nn_config(tmp_path)


def test_load_nn_config_non_mapping_root_raises(tmp_path):
    (tmp_path / "nn-config.yaml").write_text("- just\n- a\n- list\n", encoding="utf-8")
    if str(SCRIPTS) not in sys.path:
        sys.path.insert(0, str(SCRIPTS))
    from lib.nn_config import load_nn_config

    with pytest.raises(RuntimeError, match="mapping"):
        load_nn_config(tmp_path)
