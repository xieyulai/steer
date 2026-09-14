"""答案清单校验器。

CSI 清单（migrate）：源对齐题改回确认、其余跳问、INFO_PERM 投影；PINN 清单（build）：8 题全跳问 + strict；
坏清单三条错误；未知键 / 入口不符两条警告；template 可回读；lock 与 resolved 一致；题序 27/24 且与
hard-gate-reference「编号速查」一致。
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

SCRIPTS = Path(__file__).resolve().parent.parent
PKG = SCRIPTS.parent
sys.path.insert(0, str(SCRIPTS))

from lib import init_answers as IA  # noqa: E402

CLI = SCRIPTS / "init_answers.py"
REFERENCE = PKG.parent.parent / "skills" / "maintainer" / "auto-nn-init" / "hard-gate-reference.md"

CSI_ANSWERS = {
    "version": 1,
    "answers": {
        "训练许用材料": {
            "choice": "B",
            "eval_only_assets": ["data/data_real.npy"],
            "eval_only_readers": ["contract/test.py", "contract/prepare_data.py", "contract/data_split.py"],
        },
        "官方打分通道": {"choice": "B", "impl": "_reconstruct", "rule": "先压成 ≤64 bit 码，再只凭码还原"},
        "其他信息规矩": {"choice": "none"},
        "实验模式": {"choice": "B"},
        "主指标目标值": {"value": "none"},
        "训练墙钟": 3600,
        "GPU与并行": {"gpus": [0, 1], "max_parallel": 2},
        "复现随机性": 42,
        "数据划分": {"note": "沿源项目切分"},
    },
}

PINN_ANSWERS = {
    "version": 1,
    "answers": {
        "I1": {"choice": "C", "eval_only_assets": ["contract.test.run_ssfm"]},
        "official_path": "A",
        "其他规矩": "none",
        "实验模式": "optimize",
        "主指标目标值": {"value": 0.05},
        "训练墙钟": {"seconds": 0},
        "机器占用": {"gpus": [0], "max_parallel": 1},
        "随机种子": {"seed": 7},
    },
}


@pytest.fixture(scope="module")
def registry() -> IA.Registry:
    return IA.load_registry()


def _run(*args: str, cwd: Path | None = None) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, str(CLI), *args], capture_output=True, text=True, cwd=str(cwd or SCRIPTS))


# ── 题库 ────────────────────────────────────────────────────────────────


def test_registry_shape(registry):
    slugs = [q.slug for q in registry.questions]
    assert len(slugs) == 29 and len(set(slugs)) == 29  # 27 计步 + P0 + F1
    assert {"I1-train-consumes", "I2-official-path", "I3-other-info-rules"} <= set(slugs)
    skippable = {q.slug for q in registry.questions if q.skip_allowed}
    assert skippable == {
        "I1-train-consumes", "I2-official-path", "I3-other-info-rules",
        "G1-experiment-mode", "G2-goal-value", "O1-time-budget", "O2-gpus-parallel", "O4-repro-determinism",
    }


def test_steps_27_and_24_with_I_after_D2(registry):
    a, b = IA.steps_for(registry, "migrate"), IA.steps_for(registry, "build")
    assert len(a) == 27 and len(b) == 24
    assert a[:6] == ["D1-scenario-inventory", "D2-data-split", "I1-train-consumes", "I2-official-path",
                     "I3-other-info-rules", "D3-workspace-data"]
    assert b == [s for s in a if not s.startswith("H")]
    assert IA.steps_for(registry, "update") == []


def test_steps_match_reference_quick_table(registry):
    """reference「入口 A — 27 项速查」表里的 slug 序列 == 题库 A 题序。"""
    if not REFERENCE.is_file():
        pytest.skip("维护仓 reference 不在（业务仓）")
    text = REFERENCE.read_text(encoding="utf-8")
    start = text.index("### 入口 A — ")
    end = text.index("### 入口 B — ", start)
    rows = [ln for ln in text[start:end].splitlines() if ln.startswith("| ") and ln[2].isdigit()]
    slugs = []
    for ln in rows:
        cells = [c.strip() for c in ln.strip("|").split("|")]
        slugs.append(cells[1].strip("* `"))
    assert slugs == IA.steps_for(registry, "migrate")


def test_find_by_key_alias_slug_prefix(registry):
    q = registry.by_slug("I1-train-consumes")
    for k in ("训练许用材料", "train_consumes", "I1-train-consumes", "I1", "i1", "训练可以用哪些材料"):
        assert registry.find(k) is q, k
    assert registry.find("不存在的题") is None


# ── CSI（migrate）────────────────────────────────────────────────────────


def test_csi_migrate_resolves(registry):
    res = IA.validate_answers(registry, CSI_ANSWERS, workflow="migrate")
    assert res.ok, res.errors
    r = res.resolved
    assert set(r) == {"I1-train-consumes", "I2-official-path", "I3-other-info-rules", "G1-experiment-mode",
                      "G2-goal-value", "O1-time-budget", "O2-gpus-parallel", "O4-repro-determinism"}
    # 源对齐题：迁入须改回确认，不跳卡
    for s in ("I1-train-consumes", "I2-official-path"):
        assert r[s].confirm_required and not r[s].skip_ui
    for s in ("I3-other-info-rules", "G1-experiment-mode", "G2-goal-value", "O1-time-budget",
              "O2-gpus-parallel", "O4-repro-determinism"):
        assert r[s].skip_ui and not r[s].confirm_required, s
    assert r["I1-train-consumes"].lock == (
        "I1.CONSUMES=train_split_only; I1.EVAL_ONLY=[data/data_real.npy]; "
        "I1.READERS=[contract/test.py,contract/prepare_data.py,contract/data_split.py]; I1.STRICT=no"
    )
    assert r["I2-official-path"].lock.startswith("I2.PATH=restricted; I2.IMPL=_reconstruct; I2.RULE=先压成")
    assert r["G2-goal-value"].lock == "G2.GOAL=none; G2.FLOOR=none"
    assert r["O1-time-budget"].lock == "O1.TIME_BUDGET=3600"
    assert r["O2-gpus-parallel"].lock == "O2.GPUS=[0,1]; O2.MAX_PARALLEL=2"
    assert r["O4-repro-determinism"].lock == "O4.SEED=42"
    assert r["I1-train-consumes"].step == 3 and r["O4-repro-determinism"].step == 27
    # 未登记题只作参考
    assert "D2-data-split" in res.reference_only
    assert any("数据划分" in w for w in res.warnings)
    # 来源标记
    assert r["I3-other-info-rules"].user_text.startswith("（来自清单）none ")


def test_csi_info_perm_flags(registry):
    res = IA.validate_answers(registry, CSI_ANSWERS, workflow="migrate")
    f = res.info_perm_flags
    assert f[:2] == ["--consumes", "B"]
    assert f.count("--eval-only-readers") == 3 and "--strict-no-train-files" not in f
    i = f.index("--official-path")
    assert f[i + 1] == "B" and "--official-path-impl" in f and "_reconstruct" in f
    assert f[f.index("--other-rules") + 1] == "均无"
    assert f[-2:] == ["--enforce", "yes"]


# ── PINN（build）────────────────────────────────────────────────────────


def test_pinn_build_all_skip_and_strict(registry):
    res = IA.validate_answers(registry, PINN_ANSWERS, workflow="build")
    assert res.ok, res.errors
    assert len(res.resolved) == 8 and all(i.skip_ui for i in res.resolved.values())
    assert not any(i.confirm_required for i in res.resolved.values())  # build 无源对齐
    i1 = res.resolved["I1-train-consumes"]
    assert i1.choice == "C" and i1.lock.endswith("I1.STRICT=yes")
    assert "contract.test.run_ssfm" in i1.lock and "contract/test.py" in i1.lock  # 读者默认
    assert res.resolved["G1-experiment-mode"].choice == "B"  # value 'optimize' → 字母
    assert res.resolved["G2-goal-value"].lock == "G2.GOAL=0.05; G2.FLOOR=none"
    assert res.resolved["O1-time-budget"].lock == "O1.TIME_BUDGET=0"
    assert "--strict-no-train-files" in res.info_perm_flags
    assert res.info_perm_flags[res.info_perm_flags.index("--official-path") + 1] == "A"
    assert res.info_perm_flags[-2:] == ["--enforce", "yes"]


# ── 坏清单 / 警告 ───────────────────────────────────────────────────────


def test_bad_answers_three_errors(registry):
    bad = {
        "version": 1,
        "answers": {
            "训练许用材料": {"choice": "B"},                       # 缺 eval_only_assets
            "实验模式": "E",
            "主指标目标值": {"value": 0.9},                        # explore + 数值目标
            "GPU与并行": {"gpus": [0], "max_parallel": 4},        # 并行 > 卡数
        },
    }
    res = IA.validate_answers(registry, bad, workflow="build")
    assert not res.ok
    joined = "\n".join(res.errors)
    assert "必须填 eval_only_assets" in joined
    assert "[X-G1G2]" in joined
    assert "[X-O2]" in joined
    assert len(res.errors) == 3
    # 有错误时全部不跳卡
    assert all(not i.skip_ui for i in res.resolved.values())


def test_invalid_choice_type_and_version(registry):
    res = IA.validate_answers(registry, {"version": 1, "answers": {"实验模式": "Z", "训练墙钟": "abc"}}, workflow="build")
    assert not res.ok and len(res.errors) == 2
    res2 = IA.validate_answers(registry, {"answers": {"实验模式": "B"}}, workflow="build")
    assert any("version" in e for e in res2.errors)
    res3 = IA.validate_answers(registry, {"version": 9, "answers": {"实验模式": "B"}}, workflow="build")
    assert any("version" in e for e in res3.errors)


def test_unknown_key_and_wrong_entry_warn_only(registry):
    doc = {"version": 1, "answers": {"旧成绩与产物": {"note": "不带"}, "乱键": 1, "实验模式": "B"}}
    res = IA.validate_answers(registry, doc, workflow="build")
    assert res.ok
    assert res.unknown_keys == ["乱键"]
    assert sum("入口无此题" in w for w in res.warnings) == 1
    assert sum("未知键" in w for w in res.warnings) == 1
    assert set(res.resolved) == {"G1-experiment-mode"}


def test_bad_workflow_raises(registry):
    with pytest.raises(IA.AnswersError):
        IA.validate_answers(registry, CSI_ANSWERS, workflow="nope")


# ── template / lock / CLI ───────────────────────────────────────────────


def test_template_roundtrip(registry):
    text = IA.render_template(registry, "build")
    doc = yaml.safe_load(text)
    res = IA.validate_answers(registry, doc, workflow="build")
    assert res.ok, res.errors
    assert len(res.resolved) == 8


def test_cli_validate_write_resolved_and_rc(tmp_path):
    ans = tmp_path / "csi.yaml"
    ans.write_text(yaml.safe_dump(CSI_ANSWERS, allow_unicode=True), encoding="utf-8")
    repo = tmp_path / "repo"
    repo.mkdir()
    r = _run("validate", "--answers", str(ans), "--workflow", "migrate", "--repo-root", str(repo), "--write-resolved")
    assert r.returncode == 0, r.stdout + r.stderr
    out = json.loads((repo / ".auto-nn" / "init-answers.resolved.json").read_text(encoding="utf-8"))
    assert out["ok"] and out["resolved"]["I1-train-consumes"]["confirm_required"] is True
    assert out["resolved"]["I3-other-info-rules"]["user_text"].startswith("（来自清单）")
    assert "init_info_perm.py write" in r.stdout
    # 坏清单 rc 1
    bad = tmp_path / "bad.yaml"
    bad.write_text(yaml.safe_dump({"version": 1, "answers": {"实验模式": "Z"}}, allow_unicode=True), encoding="utf-8")
    assert _run("validate", "--answers", str(bad), "--workflow", "build").returncode == 1
    # 缺文件 rc 2；拒绝 template/package
    assert _run("validate", "--answers", str(tmp_path / "nope.yaml"), "--workflow", "build").returncode == 2
    r3 = _run("validate", "--answers", str(ans), "--workflow", "migrate", "--repo-root", str(PKG), "--write-resolved")
    assert r3.returncode == 2 and "template/package" in r3.stderr


def test_cli_lock_steps_template():
    r = _run("lock", "--slug", "I1", "--choice", "B", "--field", "eval_only_assets=data/x.npy",
             "--field", "eval_only_readers=contract/test.py,contract/prepare_data.py")
    assert r.returncode == 0
    assert r.stdout.strip() == ("I1.CONSUMES=train_split_only; I1.EVAL_ONLY=[data/x.npy]; "
                                "I1.READERS=[contract/test.py,contract/prepare_data.py]; I1.STRICT=no")
    assert _run("lock", "--slug", "I2", "--choice", "B").returncode == 1  # 缺 impl/rule
    r2 = _run("steps", "--workflow", "build")
    lines = r2.stdout.strip().splitlines()
    assert len(lines) == 24 and lines[2].endswith("I1-train-consumes")
    r3 = _run("template", "--workflow", "migrate")
    assert r3.returncode == 0 and "version: 1" in r3.stdout and "训练许用材料" in r3.stdout


CSI_CONFIRM = SCRIPTS / "tests" / "fixtures" / "csi-short-code.answers.yaml"


@pytest.mark.skipif(not CSI_CONFIRM.is_file(), reason="CSI 完整答卷举例 fixture 缺失")
def test_csi_confirm_only_covers_all_migrate_steps(registry):
    doc = yaml.safe_load(CSI_CONFIRM.read_text(encoding="utf-8"))
    res = IA.validate_answers(registry, doc, workflow="migrate")
    assert res.ok, res.errors
    assert res.confirm_only
    needed = ["P0-project-brief"] + IA.steps_for(registry, "migrate")
    assert set(res.resolved) == set(needed)
    assert all(i.skip_ui and not i.confirm_required for i in res.resolved.values())
    assert "F1-contract" not in res.resolved
    assert res.resolved["I2-official-path"].fields["impl"] == "_reconstruct"
    r = _run("validate", "--answers", str(CSI_CONFIRM), "--workflow", "migrate")
    assert r.returncode == 0
    assert "只出口径汇总签字" in r.stdout


@pytest.mark.skipif(not CSI_CONFIRM.is_file(), reason="维护仓 CSI 举例不在业务仓")
def test_confirm_only_missing_step_fails(registry):
    doc = yaml.safe_load(CSI_CONFIRM.read_text(encoding="utf-8"))
    del doc["answers"]["场景清单"]
    res = IA.validate_answers(registry, doc, workflow="migrate")
    assert not res.ok
    assert any("缺：" in e and "D1-scenario-inventory" in e for e in res.errors)
    assert all(not i.skip_ui for i in res.resolved.values())


# ── 草稿识别 / 猜测 / 导出 ─────────────────────────────────────────────


def test_peek_answers_kind_yaml_vs_md(tmp_path):
    y = tmp_path / "a.yaml"
    y.write_text("version: 1\nanswers:\n  实验模式: B\n", encoding="utf-8")
    md = tmp_path / "notes.md"
    md.write_text("# 笔记\n训练只用训练集，测试集打分才打开。\n", encoding="utf-8")
    txt = tmp_path / "x.txt"
    txt.write_text("随便一段话", encoding="utf-8")
    assert IA.peek_answers_kind(y) == "answers"
    assert IA.peek_answers_kind(md) == "draft"
    assert IA.peek_answers_kind(txt) == "draft"
    r = _run("classify", "--answers", str(md))
    assert r.returncode == 0 and r.stdout.strip() == "draft"
    r2 = _run("classify", "--answers", str(y))
    assert r2.returncode == 0 and r2.stdout.strip() == "answers"


def test_guessed_does_not_skip_ui(registry):
    doc = {
        "version": 1,
        "answers": {
            "实验模式": {"choice": "B", "guessed": True},
            "训练墙钟": 3600,
        },
    }
    res = IA.validate_answers(registry, doc, workflow="build")
    assert res.ok, res.errors
    assert res.resolved["G1-experiment-mode"].guessed
    assert not res.resolved["G1-experiment-mode"].skip_ui
    assert res.resolved["O1-time-budget"].skip_ui
    assert any("猜测" in w for w in res.warnings)


def test_invert_lock_roundtrip_skippable(registry):
    i1 = registry.by_slug("I1-train-consumes")
    lock = IA.render_lock(
        i1, "B",
        {"eval_only_assets": ["data/x.npy"], "eval_only_readers": ["contract/test.py"]},
    )
    got = IA.invert_lock(i1, lock)
    assert got is not None
    choice, fields = got
    assert choice == "B"
    assert fields["eval_only_assets"] == ["data/x.npy"]
    g1 = registry.by_slug("G1-experiment-mode")
    assert IA.invert_lock(g1, "G1.MODE=optimize") == ("B", {})
    o2 = registry.by_slug("O2-gpus-parallel")
    lock2 = IA.render_lock(o2, None, {"gpus": [0, 1], "max_parallel": 2})
    _, f2 = IA.invert_lock(o2, lock2)
    assert f2["gpus"] == [0, 1] and f2["max_parallel"] == 2
    g2 = registry.by_slug("G2-goal-value")
    lock3 = IA.render_lock(g2, None, {"value": None, "floor": None})
    _, f3 = IA.invert_lock(g2, lock3)
    assert f3["value"] is None


def test_export_from_qa_log_latest_rev(tmp_path, registry):
    from lib import init_qa_log as QL

    QL.init_header(tmp_path, workflow="build", target_root=str(tmp_path))
    QL.append_entry(
        tmp_path, step="准备", total=24, slug="P0-project-brief", theme="对齐理解",
        ask="理解对吗", options="A/B", user="分类任务 CIFAR", lock="P0=cifar-cls",
    )
    i1 = registry.by_slug("I1-train-consumes")
    lock_b = IA.render_lock(
        i1, "B",
        {"eval_only_assets": ["data/test.npy"], "eval_only_readers": ["contract/test.py"]},
    )
    QL.append_entry(
        tmp_path, step="3", total=24, slug="I1-train-consumes", theme="信息权限",
        ask="训练用什么", options="A/B/C", user="A", lock="I1.CONSUMES=all; I1.EVAL_ONLY=[]; I1.STRICT=no",
    )
    QL.append_entry(
        tmp_path, step="3", total=24, slug="I1-train-consumes", theme="信息权限",
        ask="训练用什么", options="A/B/C", user="B", lock=lock_b,
    )
    QL.append_entry(
        tmp_path, step="11", total=24, slug="G1-experiment-mode", theme="实验目标",
        ask="模式", options="A-F", user="B", lock="G1.MODE=optimize",
    )
    r = _run("export", "--repo-root", str(tmp_path), "--workflow", "build")
    assert r.returncode == 0, r.stdout + r.stderr
    out = tmp_path / ".auto-nn" / "init-answers.yaml"
    assert out.is_file()
    doc = yaml.safe_load(out.read_text(encoding="utf-8"))
    assert doc["version"] == 1 and doc["exported"] is True
    assert doc["confirm_only"] is False  # 只写了部分题
    assert doc["answers"]["训练许用材料"]["choice"] == "B"
    assert "data/test.npy" in doc["answers"]["训练许用材料"]["eval_only_assets"]
    assert doc["answers"]["实验模式"]["choice"] == "B"
    assert "缺题" in r.stdout
    # 草稿路径走 validate 应 rc 2
    md = tmp_path / "n.md"
    md.write_text("不是答卷", encoding="utf-8")
    assert _run("validate", "--answers", str(md), "--workflow", "build").returncode == 2


def test_data_loss_button_off_projects_enforce_yes(registry):
    doc = {
        "version": 1,
        "answers": {
            **PINN_ANSWERS["answers"],
            "训练里什么能动": {
                "user": "必须留着初值+方程残差",
                "lock": "T1.HARD=ic+pde",
                "common_try": {"data_loss": "no"},
            },
        },
    }
    # T1 skip_allowed=false：非 confirm_only 时只作参考，flags 仍默认 enforce yes
    res = IA.validate_answers(registry, doc, workflow="build")
    assert res.ok, res.errors
    assert res.info_perm_flags[-2:] == ["--enforce", "yes"]


def test_data_loss_on_with_i1_all_projects_enforce_no(registry):
    doc = {
        "version": 1,
        "confirm_only": True,
        "answers": _confirm_stub_answers(
            i1={"choice": "A"},
            t1={
                "user": "必须留着初值+方程残差；可以加场监督",
                "lock": "T1.HARD=ic+pde; T1.ALLOW=data-loss",
                "common_try": {"data_loss": "yes"},
            },
        ),
    }
    res = IA.validate_answers(registry, doc, workflow="migrate")
    assert res.ok, res.errors
    assert res.resolved["T1-loss-layers"].fields.get("data_loss") is True
    assert res.info_perm_flags[-2:] == ["--enforce", "no"]
    assert "--consumes" in res.info_perm_flags and res.info_perm_flags[res.info_perm_flags.index("--consumes") + 1] == "A"


def test_data_loss_on_with_i1_no_files_is_cdl1(registry):
    doc = {
        "version": 1,
        "confirm_only": True,
        "answers": _confirm_stub_answers(
            i1={"choice": "C", "eval_only_assets": ["data/fig5_ssfm.mat"]},
            t1={
                "user": "可以加场监督",
                "lock": "T1.ALLOW=data-loss",
                "common_try": {"data_loss": True},
            },
        ),
    }
    res = IA.validate_answers(registry, doc, workflow="migrate")
    assert not res.ok
    assert any(e.startswith("[C-DL1]") for e in res.errors)


def _confirm_stub_answers(*, i1: dict, t1: dict) -> dict:
    """最小 confirm_only 迁入答卷：除 I1/T1 外用占位 lock。"""
    needed = {
        "对齐理解": {"user": "pinn-fig5", "lock": "P0=fiber-nlse-pinn"},
        "场景清单": {"user": "fig5", "lock": "D1=fig5"},
        "数据划分": {"user": "no-split", "lock": "D2=no-split-files"},
        "训练许用材料": i1,
        "官方打分通道": {"choice": "A"},
        "其他信息规矩": {"choice": "none"},
        "训内数据处理": {"user": "collocation", "lock": "D3=workspace-collocation"},
        "复现数据": {"user": "mat", "lock": "D4=lock-data-root"},
        "旧成绩与产物": {"user": "discard", "lock": "H1=discard"},
        "旧经验文档": {"user": "discard", "lock": "H2=discard"},
        "旧文档硬规则": {"user": "none", "lock": "H3=none"},
        "训练里什么能动": t1,
        "调用链": {"user": "adam+lbfgs", "lock": "T2=adam-lbfgs"},
        "主辅指标": {"user": "rel_l2", "lock": "E1.primary=rel_l2"},
        "实验模式": {"choice": "B"},
        "主指标目标值": {"value": 0.01},
        "指标列分级": {"user": "primary", "lock": "E2=primary"},
        "官方终评": {"user": "test", "lock": "E3=contract.test"},
        "训内评估": {"user": "phy", "lock": "E4_PATH=phy-residual-only; E4_训内节奏=A"},
        "记录表列": {"user": "four", "lock": "E5=four-zones"},
        "场景探索方案": {"user": "fig5", "lock": "E6=single-fig5"},
        "运行参数进表": {"user": "default", "lock": "E7=default"},
        "模型存档": {"user": "last", "lock": "E8=last"},
        "怎么算更好": {"user": "rel", "lock": "keep.mode=relative"},
        "训练墙钟": {"seconds": 600},
        "GPU与并行": {"gpus": [0], "max_parallel": 1},
        "起步尺子": {"user": "plain", "lock": "O3=plain"},
        "复现随机性": {"seed": 42},
    }
    return needed

