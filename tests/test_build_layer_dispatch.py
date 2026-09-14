# tests/test_build_layer_dispatch.py
"""WP1: build_optimizer / build_scheduler cfg 分派 + no-fallback 单测。

用 importlib 从具体路径加载各 workspace 模块(package + 3 skeleton),
Workspace.__new__(Workspace) 跳过 __init__(build_* 不依赖 self)。
"""
import importlib.util
import pathlib
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent


def _load_ws(rel_path: str, mod_name: str):
    """从 template/<rel>/workspace/__init__.py 加载模块,返回 Workspace 类。"""
    pkg_dir = str(ROOT / "template" / rel_path)
    if pkg_dir not in sys.path:
        sys.path.insert(0, pkg_dir)  # 让 `from experiment import ExperimentBase` 解析
    ws_file = ROOT / "template" / rel_path / "workspace" / "__init__.py"
    spec = importlib.util.spec_from_file_location(mod_name, ws_file)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[mod_name] = mod
    spec.loader.exec_module(mod)
    return mod.Workspace


def _ws_instance(Workspace_cls):
    """build_* 不依赖 self → 跳过 __init__ 直接造空实例。"""
    return Workspace_cls.__new__(Workspace_cls)


# ── package: build_optimizer 分派 ──────────────────────────────
@pytest.fixture(scope="module")
def pkg_ws():
    return _load_ws("package", "pkg_workspace")


def test_pkg_optimizer_adam(pkg_ws):
    import torch.nn as nn
    ws = _ws_instance(pkg_ws)
    model = nn.Linear(2, 2)
    opt, meta = ws.build_optimizer(model, {"OPTIMIZER": "adam", "LR": 0.1, "WEIGHT_DECAY": 0.0})
    import torch.optim as optim
    assert isinstance(opt, optim.Adam)
    assert meta["LR"] == 0.1 and meta["OPTIMIZER"] == "adam"


def test_pkg_optimizer_adamw(pkg_ws):
    import torch.nn as nn
    import torch.optim as optim
    ws = _ws_instance(pkg_ws)
    opt, meta = ws.build_optimizer(nn.Linear(2, 2), {"OPTIMIZER": "adamw", "LR": 0.1, "WEIGHT_DECAY": 0.01})
    assert isinstance(opt, optim.AdamW)
    assert meta["OPTIMIZER"] == "adamw"


def test_pkg_optimizer_sgd(pkg_ws):
    import torch.nn as nn
    import torch.optim as optim
    ws = _ws_instance(pkg_ws)
    opt, meta = ws.build_optimizer(nn.Linear(2, 2), {"OPTIMIZER": "sgd", "LR": 0.1, "WEIGHT_DECAY": 0.0, "MOMENTUM": 0.9})
    assert isinstance(opt, optim.SGD)
    assert meta["OPTIMIZER"] == "sgd" and meta["MOMENTUM"] == 0.9


def test_pkg_optimizer_unknown_raises(pkg_ws):
    import torch.nn as nn
    ws = _ws_instance(pkg_ws)
    with pytest.raises(KeyError):
        ws.build_optimizer(nn.Linear(2, 2), {"OPTIMIZER": "lion", "LR": 0.1, "WEIGHT_DECAY": 0.0})


def test_pkg_optimizer_case_insensitive(pkg_ws):
    import torch.nn as nn
    import torch.optim as optim
    ws = _ws_instance(pkg_ws)
    opt, _ = ws.build_optimizer(nn.Linear(2, 2), {"OPTIMIZER": " ADAM ", "LR": 0.1, "WEIGHT_DECAY": 0.0})
    assert isinstance(opt, optim.Adam)


# ── package: build_scheduler no-fallback ───────────────────────
def _dummy_optimizer():
    import torch.nn as nn
    import torch.optim as optim
    return optim.SGD(nn.Linear(2, 2).parameters(), lr=0.1)


def test_pkg_scheduler_cosine(pkg_ws):
    ws = _ws_instance(pkg_ws)
    import torch.optim as optim
    sched, meta = ws.build_scheduler(_dummy_optimizer(), {"SCHEDULER": "cosine", "EPOCHS": 10})
    assert isinstance(sched, optim.lr_scheduler.CosineAnnealingLR)
    assert meta["SCHEDULER"] == "cosine"


def test_pkg_scheduler_none_returns_nullscheduler(pkg_ws):
    ws = _ws_instance(pkg_ws)
    sched, meta = ws.build_scheduler(_dummy_optimizer(), {"SCHEDULER": "none"})
    # 具名 no-op,非 None
    assert sched is not None
    assert type(sched).__name__ == "_NullScheduler"
    # 无副作用:step() 可调用不报错
    sched.step()
    assert meta["SCHEDULER"] == "none"


def test_pkg_scheduler_unknown_raises(pkg_ws):
    ws = _ws_instance(pkg_ws)
    with pytest.raises(KeyError):
        ws.build_scheduler(_dummy_optimizer(), {"SCHEDULER": "lambda"})


def test_pkg_scheduler_step_returns_steplr(pkg_ws):
    ws = _ws_instance(pkg_ws)
    import torch.optim as optim
    cfg = {"OPTIMIZER": "sgd", "SCHEDULER": "step", "LR": 0.01, "STEP_SIZE": 10, "GAMMA": 0.1}
    sched, meta = ws.build_scheduler(_dummy_optimizer(), cfg)
    assert isinstance(sched, optim.lr_scheduler.StepLR)
    assert meta["SCHEDULER"] == "step"


def test_pkg_scheduler_missing_key_raises(pkg_ws):
    ws = _ws_instance(pkg_ws)
    with pytest.raises(KeyError):
        ws.build_scheduler(_dummy_optimizer(), {"LR": 0.01, "STEP_SIZE": 10, "GAMMA": 0.1})


# ── supervised skeleton ────────────────────────────────────────
@pytest.fixture(scope="module")
def sup_ws():
    # Skeleton 自带目录无 experiment.py;借 package 仓的 experiment.py 满足 `from experiment import`
    pkg_root = str(ROOT / "template" / "package")
    if pkg_root not in sys.path:
        sys.path.insert(0, pkg_root)
    return _load_ws("maintainer/skeletons/supervised", "sup_workspace")


def test_sup_optimizer_adamw_strict_read(sup_ws):
    """supervised 原写死 AdamW + cfg.get(LR,默认);改后 OPTIMIZER=adamw 且强读。"""
    import torch.nn as nn
    import torch.optim as optim
    ws = _ws_instance(sup_ws)
    opt, meta = ws.build_optimizer(nn.Linear(2, 2), {"OPTIMIZER": "adamw", "LR": 0.05, "WEIGHT_DECAY": 0.01})
    assert isinstance(opt, optim.AdamW)
    assert meta["OPTIMIZER"] == "adamw" and meta["LR"] == 0.05


def test_sup_optimizer_missing_key_raises(sup_ws):
    """G-cfg-no-defaults:缺 OPTIMIZER → KeyError(强读,非 cfg.get 兜底默认)。"""
    import torch.nn as nn
    ws = _ws_instance(sup_ws)
    with pytest.raises(KeyError):
        ws.build_optimizer(nn.Linear(2, 2), {"LR": 0.05, "WEIGHT_DECAY": 0.01})


def test_sup_scheduler_none_returns_nullscheduler(sup_ws):
    ws = _ws_instance(sup_ws)
    sched, _ = ws.build_scheduler(_dummy_optimizer(), {"SCHEDULER": "none"})
    assert sched is not None and type(sched).__name__ == "_NullScheduler"


def test_sup_scheduler_unknown_raises(sup_ws):
    ws = _ws_instance(sup_ws)
    with pytest.raises(KeyError):
        ws.build_scheduler(_dummy_optimizer(), {"SCHEDULER": "whatever"})


def test_sup_scheduler_step_returns_steplr(sup_ws):
    ws = _ws_instance(sup_ws)
    import torch.optim as optim
    cfg = {"OPTIMIZER": "sgd", "SCHEDULER": "step", "LR": 0.01, "STEP_SIZE": 10, "GAMMA": 0.1}
    sched, meta = ws.build_scheduler(_dummy_optimizer(), cfg)
    assert isinstance(sched, optim.lr_scheduler.StepLR)
    assert meta["SCHEDULER"] == "step"


def test_sup_scheduler_missing_key_raises(sup_ws):
    ws = _ws_instance(sup_ws)
    with pytest.raises(KeyError):
        ws.build_scheduler(_dummy_optimizer(), {"LR": 0.01, "STEP_SIZE": 10, "GAMMA": 0.1})


# ── rl skeleton ────────────────────────────────────────────────
@pytest.fixture(scope="module")
def rl_ws():
    # 沿用 sup fixture 模式:借 package 仓的 experiment.py 满足 `from experiment import`
    pkg_root = str(ROOT / "template" / "package")
    if pkg_root not in sys.path:
        sys.path.insert(0, pkg_root)
    return _load_ws("maintainer/skeletons/rl", "rl_workspace")


def test_rl_optimizer_adam_strict_read(rl_ws):
    """rl 原写死 Adam + cfg.get(LR,3e-4);改后 OPTIMIZER=adam 且强读 cfg["LR"]。"""
    import torch.nn as nn
    import torch.optim as optim
    ws = _ws_instance(rl_ws)
    opt, meta = ws.build_optimizer(nn.Linear(2, 2), {"OPTIMIZER": "adam", "LR": 3e-4, "WEIGHT_DECAY": 0.0})
    assert isinstance(opt, optim.Adam)
    assert meta["OPTIMIZER"] == "adam" and meta["LR"] == 3e-4


def test_rl_optimizer_missing_key_raises(rl_ws):
    """G-cfg-no-defaults:缺 OPTIMIZER → KeyError(强读,非 cfg.get 兜底默认)。"""
    import torch.nn as nn
    ws = _ws_instance(rl_ws)
    with pytest.raises(KeyError):
        ws.build_optimizer(nn.Linear(2, 2), {"LR": 3e-4, "WEIGHT_DECAY": 0.0})


def test_rl_scheduler_none_returns_nullscheduler(rl_ws):
    """rl 原裸 return None,{};改后 none→_NullScheduler(具名 no-op)。"""
    ws = _ws_instance(rl_ws)
    sched, meta = ws.build_scheduler(_dummy_optimizer(), {"SCHEDULER": "none"})
    assert sched is not None and type(sched).__name__ == "_NullScheduler"
    assert meta["SCHEDULER"] == "none"


def test_rl_scheduler_step_returns_steplr(rl_ws):
    ws = _ws_instance(rl_ws)
    import torch.optim as optim
    cfg = {"OPTIMIZER": "sgd", "SCHEDULER": "step", "LR": 0.01, "STEP_SIZE": 10, "GAMMA": 0.1}
    sched, meta = ws.build_scheduler(_dummy_optimizer(), cfg)
    assert isinstance(sched, optim.lr_scheduler.StepLR)
    assert meta["SCHEDULER"] == "step"


def test_rl_scheduler_missing_key_raises(rl_ws):
    ws = _ws_instance(rl_ws)
    with pytest.raises(KeyError):
        ws.build_scheduler(_dummy_optimizer(), {"LR": 0.01, "STEP_SIZE": 10, "GAMMA": 0.1})


# ── physical skeleton ──────────────────────────────────────────
@pytest.fixture(scope="module")
def physical_ws():
    # 沿用 sup/rl fixture 模式:借 package 仓的 experiment.py 满足 `from experiment import`
    pkg_root = str(ROOT / "template" / "package")
    if pkg_root not in sys.path:
        sys.path.insert(0, pkg_root)
    return _load_ws("maintainer/skeletons/physical", "physical_workspace")


# WP1③:physical 不再读 cfg["OPTIMIZER"],改读 cfg["OPTIMIZER_SCHEME"](β named scheme)
def test_physical_scheme_adam_strict_read(physical_ws):
    """OPTIMIZER_SCHEME="adam" 单阶段 → 返回 Adam + STAGES=["adam"]。"""
    import torch.nn as nn
    import torch.optim as optim
    ws = _ws_instance(physical_ws)
    opt, meta = ws.build_optimizer(
        nn.Linear(2, 2),
        {"OPTIMIZER_SCHEME": "adam", "LR": 1e-3, "WEIGHT_DECAY": 0.0},
    )
    assert isinstance(opt, optim.Adam)
    assert meta["OPTIMIZER_SCHEME"] == "adam" and meta["LR"] == 1e-3
    assert meta["STAGES"] == ["adam"]


def test_physical_scheme_lbfgs_returns_lbfgs(physical_ws):
    """OPTIMIZER_SCHEME="lbfgs" 单阶段 → 返回 LBFGS(强读 LBFGS_MAX_ITER)。"""
    import torch.nn as nn
    import torch.optim as optim
    ws = _ws_instance(physical_ws)
    opt, meta = ws.build_optimizer(
        nn.Linear(2, 2),
        {"OPTIMIZER_SCHEME": "lbfgs", "LR": 1.0, "LBFGS_MAX_ITER": 20},
    )
    assert isinstance(opt, optim.LBFGS)
    assert meta["OPTIMIZER_SCHEME"] == "lbfgs"
    assert meta["LBFGS_MAX_ITER"] == 20
    assert meta["STAGES"] == ["lbfgs"]


def test_physical_scheme_adam_lbfgs_returns_adam_with_stage_marker(physical_ws):
    """β 经典分阶段:返回 Adam + STAGES=["adam","lbfgs"](LBFGS 切换留给 train_step,WP3 边界)。"""
    import torch.nn as nn
    import torch.optim as optim
    ws = _ws_instance(physical_ws)
    opt, meta = ws.build_optimizer(
        nn.Linear(2, 2),
        {"OPTIMIZER_SCHEME": "adam_lbfgs", "LR": 1e-3, "WEIGHT_DECAY": 0.0},
    )
    assert isinstance(opt, optim.Adam), "adam_lbfgs 第 1 阶段应返 Adam"
    assert meta["OPTIMIZER_SCHEME"] == "adam_lbfgs"
    assert meta["STAGES"] == ["adam", "lbfgs"], "STAGES 标 2 阶段,供 train_step 切换"


def test_physical_scheme_unknown_raises(physical_ws):
    """no-fallback:未知 OPTIMIZER_SCHEME → KeyError(新 = 在 build_optimizer 加 elif 分支)。"""
    import torch.nn as nn
    ws = _ws_instance(physical_ws)
    with pytest.raises(KeyError, match="OPTIMIZER_SCHEME"):
        ws.build_optimizer(
            nn.Linear(2, 2),
            {"OPTIMIZER_SCHEME": "rmsprop", "LR": 1e-3, "WEIGHT_DECAY": 0.0},
        )


def test_physical_scheme_missing_key_raises(physical_ws):
    """G-cfg-no-defaults:缺 OPTIMIZER_SCHEME → KeyError(强读,非 cfg.get 兜底默认)。"""
    import torch.nn as nn
    ws = _ws_instance(physical_ws)
    with pytest.raises(KeyError):
        ws.build_optimizer(nn.Linear(2, 2), {"LR": 1e-3, "WEIGHT_DECAY": 0.0})


def test_physical_scheduler_none_returns_nullscheduler(physical_ws):
    """physical 原裸 return None,{};改后 none→_NullScheduler(具名 no-op)。"""
    ws = _ws_instance(physical_ws)
    sched, meta = ws.build_scheduler(_dummy_optimizer(), {"SCHEDULER": "none"})
    assert sched is not None and type(sched).__name__ == "_NullScheduler"
    assert meta["SCHEDULER"] == "none"


def test_physical_scheduler_step_returns_steplr(physical_ws):
    ws = _ws_instance(physical_ws)
    import torch.optim as optim
    cfg = {"OPTIMIZER": "sgd", "SCHEDULER": "step", "LR": 0.01, "STEP_SIZE": 10, "GAMMA": 0.1}
    sched, meta = ws.build_scheduler(_dummy_optimizer(), cfg)
    assert isinstance(sched, optim.lr_scheduler.StepLR)
    assert meta["SCHEDULER"] == "step"


def test_physical_scheduler_missing_key_raises(physical_ws):
    """G-cfg-no-defaults:缺 SCHEDULER → KeyError(强读,非 cfg.get 兜底默认)。"""
    ws = _ws_instance(physical_ws)
    with pytest.raises(KeyError):
        ws.build_scheduler(_dummy_optimizer(), {"LR": 0.01, "STEP_SIZE": 10, "GAMMA": 0.1})
