# tests/test_dataset_registry.py
"""要求2(D-DATASET):supervised skeleton 的数据集注册表 + 范式锁死单测。

设计要点(对照记录 doc §7 Phase 2):
- 读哪个数据集锁死 = contract 常量 LOCKED_DATASET(runtime.py),Agent 不可达(不走 cfg)。
- DATASET_REGISTRY = 枚举+验证表;未知名 → KeyError(no-fallback,不静默回落 FashionMNIST)。
- 怎么处理(transform/aug/batch)可改 = 走 cfg(此处不测,见 build_dataloader/prepare_data 下游)。

不触发网络下载:happy-path 用 monkeypatch 往 registry 注入假构造器,只验分派管线。
"""
import importlib.util
import pathlib
import sys
import types

import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent
SUP_CONTRACT = ROOT / "template" / "maintainer" / "skeletons" / "supervised" / "contract"


def _load_skeleton_contract():
    """按绝对路径加载骨架层 contract 子模块,隔离 template/package 占位符。

    `contract` 是 namespace package —— 若 template/package 已在 sys.path,
    `import contract.prepare_data` 会命中占位符。故手动建一个 __path__ 只指骨架层的
    contract 包,再按路径逐个 exec runtime→prepare_data→test(prepare_data 依赖
    contract.runtime,test 依赖两者,故按此序加载)。
    """
    pkg = types.ModuleType("contract")
    pkg.__path__ = [str(SUP_CONTRACT)]  # 隔离:只认骨架层,不聚合占位符
    sys.modules["contract"] = pkg
    for sub in ("runtime", "prepare_data", "test"):
        name = f"contract.{sub}"
        spec = importlib.util.spec_from_file_location(name, SUP_CONTRACT / f"{sub}.py")
        mod = importlib.util.module_from_spec(spec)
        sys.modules[name] = mod  # 先注册,供下游 `from contract.X import` 命中
        spec.loader.exec_module(mod)
    return pkg


@pytest.fixture(scope="module", autouse=True)
def _skeleton_contract():
    """加载骨架层 contract,测完恢复 sys.modules(不污染依赖占位符的其它测试)。"""
    saved = {k: v for k, v in sys.modules.items() if k == "contract" or k.startswith("contract.")}
    for k in list(saved):
        del sys.modules[k]
    yield _load_skeleton_contract()
    for k in [k for k in sys.modules if k == "contract" or k.startswith("contract.")]:
        del sys.modules[k]
    sys.modules.update(saved)


@pytest.fixture(scope="module")
def pd():
    import contract.prepare_data as pd  # noqa: WPS433
    return pd


@pytest.fixture(scope="module")
def runtime():
    import contract.runtime as runtime  # noqa: WPS433
    return runtime


@pytest.fixture(scope="module")
def terminal_test():
    import contract.test as terminal_test  # noqa: WPS433
    return terminal_test


# ── 锁死自洽 ───────────────────────────────────────────────────
def test_locked_dataset_is_registered(pd, runtime):
    """LOCKED_DATASET 指向的身份必须在 DATASET_REGISTRY 里有构造器(否则锁死=死锁)。"""
    key = str(runtime.LOCKED_DATASET).lower().strip()
    assert key in pd.DATASET_REGISTRY, (
        f"LOCKED_DATASET={runtime.LOCKED_DATASET!r} 不在 registry,锁死身份无构造器"
    )


def test_registry_keys_lowercase(pd):
    """registry 键全小写:验证层 `str(name).lower()` 才能命中。"""
    for k in pd.DATASET_REGISTRY:
        assert k == k.lower(), f"registry 键 {k!r} 应小写"


# ── no-fallback:未知名 → KeyError(构造器调用之前)──────────────
def test_unknown_dataset_raises_before_download(pd):
    """未知数据集名 → KeyError,且在调用构造器(可能下载)之前 raise。"""
    with pytest.raises(KeyError, match="DATASET"):
        pd._build_dataset("cifar100", "/tmp/nope", train=True, transform=None)


def test_build_dataset_dispatch_with_fake_ctor(pd, monkeypatch):
    """分派管线:registry[name](root, train, transform) 透传三参(不下载)。"""
    captured = {}

    def _fake(root, train, transform):
        captured["root"] = root
        captured["train"] = train
        captured["transform"] = transform
        return ("__fake_dataset__",)

    monkeypatch.setitem(pd.DATASET_REGISTRY, "__fake__", _fake)
    out = pd._build_dataset(" __Fake__ ", "/data/x", train=False, transform="T")
    assert out == ("__fake_dataset__",)
    assert captured == {"root": "/data/x", "train": False, "transform": "T"}


# ── test.py 也走 registry(不再硬编码 datasets.FashionMNIST)─────
def test_get_test_loader_routes_through_registry(pd, terminal_test, monkeypatch):
    """get_test_loader 经 _build_dataset 构造(不下载:假 map-style 数据集)。"""

    class _FakeMapStyle:
        """最小 map-style 数据集(DataLoader 构造不迭代,只需 __len__/__getitem__)。"""

        def __len__(self):
            return 4

        def __getitem__(self, idx):
            return idx, idx

    def _fake(root, train, transform):
        assert train is False, "test split 必须 train=False"
        return _FakeMapStyle()

    # 锁死身份 fashionmnist 是真键 → 替换为假构造器避免下载
    import contract.runtime as runtime
    monkeypatch.setitem(pd.DATASET_REGISTRY, runtime.LOCKED_DATASET.lower(), _fake)

    from torch.utils.data import DataLoader
    loader = terminal_test.get_test_loader("/data/x", batch_size=2, num_workers=0)
    assert isinstance(loader, DataLoader)
