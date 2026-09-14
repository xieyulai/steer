# tests/test_mammoth_cli_adapter.py
"""WP0.4: mammoth CLI 适配器 register_cli_adapter 契约锁定。

锁以下不变量(单一 register 契约):
1. CLI_ADAPTER_REGISTRY 公开 dict(无下划线)
2. @register_cli_adapter 注册 fn 进 CLI_ADAPTER_REGISTRY
3. 重复注册同名 → KeyError(no-fallback)
4. build_command 对未知 MAMMOTH_MODEL → KeyError(no-fallback)

用 importlib 加载 mammoth workspace(借 package 仓的 experiment.py 满足
`from experiment import ExperimentBase`)。
"""
import importlib.util
import pathlib
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent


@pytest.fixture(scope="module")
def mammoth_ws():
    """加载 mammoth workspace 模块。"""
    pkg_root = str(ROOT / "template" / "package")
    scripts_root = str(ROOT / "template" / "package" / "scripts")
    for p in (scripts_root, pkg_root):
        if p not in sys.path:
            sys.path.insert(0, p)  # experiment + lib.adapter_accept
    ws_file = ROOT / "docs" / "examples" / "adapter-mammoth" / "workspace" / "__init__.py"
    spec = importlib.util.spec_from_file_location("mammoth_workspace", ws_file)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["mammoth_workspace"] = mod
    spec.loader.exec_module(mod)
    return mod


def test_cli_adapter_registry_is_public(mammoth_ws):
    """WP0.4:CLI 适配器 dict 公开命名,无下划线。"""
    assert hasattr(mammoth_ws, "CLI_ADAPTER_REGISTRY")
    assert isinstance(mammoth_ws.CLI_ADAPTER_REGISTRY, dict)
    # 反例:不再有私有 _LEARNER_REGISTRY
    assert not hasattr(mammoth_ws, "_LEARNER_REGISTRY")


def test_register_cli_adapter_decorates_fn(mammoth_ws):
    """@register_cli_adapter 应注册 fn 进 CLI_ADAPTER_REGISTRY,函数原样返回。"""
    @mammoth_ws.register_cli_adapter("__test_method__")
    def _t(cfg, args):
        args.extend(["--x", str(cfg["X"])])

    assert "__test_method__" in mammoth_ws.CLI_ADAPTER_REGISTRY
    assert mammoth_ws.CLI_ADAPTER_REGISTRY["__test_method__"] is _t


def test_register_cli_adapter_duplicate_raises(mammoth_ws):
    """G-no-fallback:同名重复注册 → KeyError(防覆盖,锁定现有实现)。"""
    with pytest.raises(KeyError):

        @mammoth_ws.register_cli_adapter("class-balanced-derpp")
        def _dup(cfg, args):
            pass


def test_build_command_unknown_model_raises(mammoth_ws, tmp_path):
    """G-no-fallback:build_command 对未知 MAMMOTH_MODEL 立即 raise KeyError。

    这是行为变更(原: silent no-op;现: 显式报错)——见 spec §3.3 单一契约要求。
    vanilla mammoth 模型(无额外参数)需要显式注册一个 no-op CLI 适配器。
    """
    # 用 tmp_path 当 MAMMOTH_ROOT 让存在性检查通过,只测 dispatch 逻辑
    cfg = {
        "MAMMOTH_ROOT": str(tmp_path),
        "MAMMOTH_DATASET": "seq-cifar10",
        "MAMMOTH_MODEL": "totally-unknown-model",
        "MAMMOTH_DATASET_CONFIG": "default",
    }
    with pytest.raises(KeyError, match="totally-unknown-model"):
        mammoth_ws.build_command(cfg, tmp_path)


def test_build_command_known_model_appends_args(mammoth_ws, tmp_path):
    """已知 MAMMOTH_MODEL="class-balanced-derpp" 走 _class_balanced_derpp,append --alpha/--beta。"""
    cfg = {
        "MAMMOTH_ROOT": str(tmp_path),  # 满足存在性,只测 dispatch
        "MAMMOTH_DATASET": "seq-cifar10",
        "MAMMOTH_MODEL": "class-balanced-derpp",
        "MAMMOTH_DATASET_CONFIG": "default",
        "LR": 0.01,
        "N_EPOCHS": 1,
        "ALPHA": 0.1,
        "BETA": 0.2,
        "CB_TAU": 0.5,
    }
    cmd = mammoth_ws.build_command(cfg, tmp_path)
    # class-balanced-derpp 必须 append --alpha/--beta/--cb_tau
    assert "--alpha" in cmd and "0.1" in cmd
    assert "--beta" in cmd and "0.2" in cmd
    assert "--cb_tau" in cmd and "0.5" in cmd


def test_build_command_omits_empty_alpha_beta(mammoth_ws, tmp_path):
    """空串 ALPHA/BETA 不追加 --alpha/--beta（白名单 + 方法专属路径均跳过）。"""
    cfg = {
        "MAMMOTH_ROOT": str(tmp_path),
        "MAMMOTH_DATASET": "seq-cifar10",
        "MAMMOTH_MODEL": "class-balanced-derpp",
        "MAMMOTH_DATASET_CONFIG": "default",
        "LR": 0.01,
        "N_EPOCHS": 1,
        "ALPHA": "",
        "BETA": "  ",
        "CB_TAU": 0.5,
    }
    cmd = mammoth_ws.build_command(cfg, tmp_path)
    assert "--alpha" not in cmd
    assert "--beta" not in cmd
    assert "--cb_tau" in cmd and "0.5" in cmd
    assert "--lr" in cmd and "0.01" in cmd