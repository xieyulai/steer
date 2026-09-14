"""Tests for DATA_SAMPLER / wrap_train_loader + train.py migrate."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest
import torch
from torch.utils.data import DataLoader, Dataset, WeightedRandomSampler

_PKG = Path(__file__).resolve().parents[2]
if str(_PKG) not in sys.path:
    sys.path.insert(0, str(_PKG))

from experiment import (  # noqa: E402
    ExperimentBase,
    SAMPLER_REGISTRY,
    rebuild_dataloader_with_sampler,
    register_sampler,
)
from scripts.lib.migrate_wrap_train_loader import migrate_source, needs_migrate  # noqa: E402


class _TinyDS(Dataset):
    def __init__(self, n: int = 8):
        self.n = n

    def __len__(self) -> int:
        return self.n

    def __getitem__(self, i: int):
        return torch.tensor([float(i)]), torch.tensor([float(i)])


@pytest.fixture(autouse=True)
def _clean_registry():
    before = dict(SAMPLER_REGISTRY)
    SAMPLER_REGISTRY.clear()
    yield
    SAMPLER_REGISTRY.clear()
    SAMPLER_REGISTRY.update(before)


def test_wrap_absent_key_noop():
    ws = ExperimentBase.__new__(ExperimentBase)
    loader = DataLoader(_TinyDS(), batch_size=2, shuffle=True)
    out = ws.wrap_train_loader(loader, {})
    assert out is loader


def test_wrap_none_uniform_noop():
    ws = ExperimentBase.__new__(ExperimentBase)
    loader = DataLoader(_TinyDS(), batch_size=2, shuffle=True)
    assert ws.wrap_train_loader(loader, {"DATA_SAMPLER": "none"}) is loader
    assert ws.wrap_train_loader(loader, {"DATA_SAMPLER": "uniform"}) is loader


def test_wrap_unknown_keyerror():
    ws = ExperimentBase.__new__(ExperimentBase)
    loader = DataLoader(_TinyDS(), batch_size=2)
    with pytest.raises(KeyError, match="DATA_SAMPLER"):
        ws.wrap_train_loader(loader, {"DATA_SAMPLER": "boundary"})


def test_wrap_registered_rebuilds():
    @register_sampler("boundary")
    def _boundary(dataset, cfg):
        w = torch.ones(len(dataset))
        w[:2] = 3.0
        return WeightedRandomSampler(w, num_samples=len(dataset), replacement=True)

    ws = ExperimentBase.__new__(ExperimentBase)
    loader = DataLoader(_TinyDS(8), batch_size=2, shuffle=True, num_workers=0)
    out = ws.wrap_train_loader(loader, {"DATA_SAMPLER": "boundary"})
    assert out is not loader
    assert out.batch_size == 2
    assert getattr(out, "sampler", None) is not None
    batch = next(iter(out))
    assert batch[0].shape[0] == 2


def test_rebuild_preserves_batch_size():
    loader = DataLoader(_TinyDS(6), batch_size=3, shuffle=True)
    sampler = WeightedRandomSampler(torch.ones(6), num_samples=6, replacement=True)
    out = rebuild_dataloader_with_sampler(loader, sampler)
    assert out.batch_size == 3
    assert len(out.dataset) == 6


def test_wrap_none_loader():
    ws = ExperimentBase.__new__(ExperimentBase)
    assert ws.wrap_train_loader(None, {"DATA_SAMPLER": "boundary"}) is None


def test_migrate_inserts_after_prepare_data():
    src = (
        "    cfg['_train_transform'] = train_transform\n"
        "    train_loader, val_loader = contract.prepare_data(cfg)\n"
        "    del cfg['_train_transform']\n"
    )
    assert needs_migrate(src)
    new, changed = migrate_source(src)
    assert changed
    assert "train_loader = ws.wrap_train_loader(train_loader, cfg)" in new
    # 紧跟 prepare_data
    lines = [ln.strip() for ln in new.splitlines() if ln.strip()]
    i = lines.index("train_loader, val_loader = contract.prepare_data(cfg)")
    assert lines[i + 1] == "train_loader = ws.wrap_train_loader(train_loader, cfg)"


def test_migrate_idempotent():
    src = (
        "    train_loader, val_loader = contract.prepare_data(cfg)\n"
        "    train_loader = ws.wrap_train_loader(train_loader, cfg)\n"
    )
    assert not needs_migrate(src)
    new, changed = migrate_source(src)
    assert not changed
    assert new == src
