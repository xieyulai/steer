"""台账表头列序必须确定（模板 4.1.1 修：overlay 键曾是 frozenset）。

背景：``_LEDGER_OVERLAY_KEYS`` 原为 frozenset ⇒ 迭代序随进程 PYTHONHASHSEED 变
⇒ ``_effective_ledger_context_keys()`` 补列顺序随机 ⇒ ``_default_tsv_columns()``
两次运行出两种表头 ⇒ verify/doctor 的 tsv_header 检查「刚 regen 完也可能 FAIL」。
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

PKG = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PKG))

from experiment import ExperimentBase, _LEDGER_OVERLAY_KEYS  # noqa: E402

_PROBE = """
import sys
sys.path.insert(0, {pkg!r})
from experiment import ExperimentBase


class C(ExperimentBase):
    @property
    def metric_keys(self):
        return {{"acc": "maximize"}}


print("\\t".join(C()._default_tsv_columns()))
"""


def _columns_in_subprocess(hashseed: str, cwd: Path) -> str:
    env = dict(os.environ, PYTHONHASHSEED=hashseed)
    proc = subprocess.run(
        [sys.executable, "-c", _PROBE.format(pkg=str(PKG))],
        cwd=str(cwd),
        env=env,
        capture_output=True,
        text=True,
        check=True,
    )
    return proc.stdout.strip()


def test_overlay_keys_are_ordered_tuple():
    """overlay 键须写成有序元组（写成集合就恢复不了列序）。"""
    assert isinstance(_LEDGER_OVERLAY_KEYS, tuple)
    assert list(_LEDGER_OVERLAY_KEYS) == [
        "exploration_space",
        "untrained",
        "rehearsal_score",
    ]


def test_tsv_header_stable_across_hashseeds(tmp_path):
    """不同 PYTHONHASHSEED 的进程，表头必须逐列相同。

    seed 取 1/3/4：这三个 seed 下 str 集合的迭代序确实不同（seed 1 与 2 恰好相同，
    只比 1/2 会漏掉回归）。曾用集合实现时，本用例必红。
    """
    columns = {seed: _columns_in_subprocess(seed, tmp_path) for seed in ("1", "3", "4")}
    assert len(set(columns.values())) == 1, columns
    cols = columns["1"].split("\t")
    assert cols[:2] == ["experiment", "scenario_id"]
    # overlay 三列按固定序紧跟在 baseline_tag / exploration_space 之后
    assert cols.index("baseline_tag") < cols.index("exploration_space")
    assert cols.index("exploration_space") < cols.index("untrained")
    assert cols.index("untrained") < cols.index("rehearsal_score")
