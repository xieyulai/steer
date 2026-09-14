"""Ticket 05 §11 主体闭环：bundle paper 段 → 可执行建议结构。

spec §11 预拍板：外部证据包加「可执行建议」{method → target_slot (ABCDE) →
cfg_mapping → 伪代码/骨架}。本切片测 build_executable_advice(paper) 纯函数：
从 method_excerpt 关键词分类落到 ABCDE 槽（B=learner/C=objective/D=augmentation），
按槽映射 cfg 键（MODEL_ARCH/LOSS/AUGMENTATION），带 paper_ref 可追溯。

纯函数（无 IO）；落盘（Slice 4 wiring）/ 骨架生成（Slice 2）/ direction_full
注入（Slice 3）在后。
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from lib.external.executable_advice import (  # noqa: E402
    attach_executable_advice,
    build_executable_advice,
    executable_advice_block,
    generate_registry_skeleton,
)


# ---- 槽分类（method_excerpt 关键词 → ABCDE 槽 + registry + cfg 键）----

def test_build_advice_arch_keywords_map_to_learner_slot_B():
    """方法摘要含架构词（architecture/backbone/conv/attention）→ B 槽 / learner / MODEL_ARCH。"""
    out = build_executable_advice({
        "method_excerpt": "We propose a residual attention architecture with conv blocks.",
        "hits": [{"title": "FooNet", "arxiv_id": "2401.00001"}],
    })
    assert out is not None
    assert out["target_slot"] == "B"
    assert out["target_registry_slot"] == "learner"
    assert "MODEL_ARCH" in out["cfg_mapping"]
    assert out["cfg_mapping"]["MODEL_ARCH"]  # 非空注册名


def test_build_advice_loss_keywords_map_to_objective_slot_C():
    """方法摘要含 loss 词（loss/contrastive/cost）→ C 槽 / objective / LOSS。"""
    out = build_executable_advice({
        "method_excerpt": "We introduce a contrastive loss function for representation learning.",
        "hits": [{"title": "InfoNCE", "arxiv_id": "2402.00002"}],
    })
    assert out["target_slot"] == "C"
    assert out["target_registry_slot"] == "objective"
    assert out["cfg_mapping"].get("LOSS")


def test_build_advice_aug_keywords_map_to_augmentation_slot_D():
    """方法摘要含增强词（augmentation/mixup/transform）→ D 槽 / augmentation / AUGMENTATION。"""
    out = build_executable_advice({
        "method_excerpt": "A novel data augmentation using mixup and cutout transforms.",
        "hits": [{"title": "MixupAug", "arxiv_id": "2403.00003"}],
    })
    assert out["target_slot"] == "D"
    assert out["target_registry_slot"] == "augmentation"
    assert out["cfg_mapping"].get("AUGMENTATION")


# ---- 空包安全（AC：空外部证据不崩；无可执行建议 → None）----

def test_build_advice_empty_paper_returns_None():
    """空 paper → 无可执行建议（None）。"""
    assert build_executable_advice({}) is None


def test_build_advice_no_method_no_hits_returns_None():
    """paper 存在但无方法摘要且无命中 → None。"""
    assert build_executable_advice({"method_excerpt": "", "hits": []}) is None


# ---- 可追溯 + 摘要（story #16 / spec §11）----

def test_build_advice_carries_paper_ref_for_traceability():
    """paper_ref 带可追溯标识（arxiv_id 优先），便于回查 bundle。"""
    out = build_executable_advice({
        "method_excerpt": "residual architecture",
        "hits": [{"title": "FooNet", "arxiv_id": "2401.00001",
                  "url": "https://arxiv.org/abs/2401.00001"}],
    })
    assert out["paper_ref"]
    assert "2401.00001" in out["paper_ref"]


def test_build_advice_has_proposed_change_text():
    """proposed_change 非空（一句话变更摘要，喂 [实现建议] 块）。"""
    out = build_executable_advice({
        "method_excerpt": "We propose a residual attention architecture.",
        "hits": [{"title": "FooNet"}],
    })
    assert out["proposed_change"]


# ---- Slice 2: generate_registry_skeleton（advice → 注册项骨架代码）----
# spec §4/§11：可执行建议落成可 exec 的注册项骨架（@register_* + TODO 类体），
# 下轮 agent 选中后填充实现 → smoke。tracer-bullet：最薄骨架，生成质量后补。

def _advice(*, slot="B", registry="learner", name="FooNet",
            cfg_key="MODEL_ARCH", paper_ref="arxiv:2401.00001",
            proposed="We propose a residual attention architecture."):
    """构造最小 advice dict（对齐 build_executable_advice 输出 schema）。"""
    return {
        "proposed_change": proposed,
        "target_slot": slot,
        "target_registry_slot": registry,
        "cfg_mapping": {cfg_key: name},
        "paper_ref": paper_ref,
    }


def test_skeleton_learner_has_register_decorator_and_compiles():
    """learner 槽骨架：@register_learner("<name>") + 类体；代码可编译（ast.parse 通过）。"""
    import ast
    skel = generate_registry_skeleton(_advice())
    code = skel["code"]
    ast.parse(code)  # 语法合法（不抛）
    assert '@register_learner("FooNet")' in code
    assert "class FooNet" in code  # 类名从注册键派生
    assert "nn.Module" in code  # learner/objective 子类 nn.Module


def test_skeleton_objective_uses_objective_registry():
    """objective 槽 → @register_objective。"""
    skel = generate_registry_skeleton(_advice(slot="C", registry="objective",
                                             name="InfoNCE", cfg_key="LOSS"))
    assert '@register_objective("InfoNCE")' in skel["code"]
    assert "class InfoNCE" in skel["code"]


def test_skeleton_augmentation_uses_augmentation_registry_and_plain_base():
    """augmentation 槽 → @register_augmentation；基类非 nn.Module（transform 不是网络）。"""
    skel = generate_registry_skeleton(_advice(slot="D", registry="augmentation",
                                             name="MixupAug", cfg_key="AUGMENTATION"))
    code = skel["code"]
    assert '@register_augmentation("MixupAug")' in code
    assert "nn.Module" not in code  # transform 不子类 nn.Module


def test_skeleton_carries_registry_name_class_name_fields():
    """返回 dict 带 registry/registry_name/class_name（喂 Slice 5 集成 + direction_full 块）。"""
    skel = generate_registry_skeleton(_advice(name="FooNet"))
    assert skel["registry"] == "learner"
    assert skel["registry_name"] == "FooNet"
    assert skel["class_name"]  # 非空类名


def test_skeleton_carries_paper_ref_and_proposed_change_for_agent():
    """骨架注释带 paper_ref + proposed_change（agent 填充时的可追溯 + 指引）。"""
    skel = generate_registry_skeleton(_advice(
        paper_ref="arxiv:2401.00001",
        proposed="We propose a residual attention architecture."))
    code = skel["code"]
    assert "2401.00001" in code  # paper_ref 可追溯
    assert "residual attention" in code  # proposed_change 指引


# ---- Slice 3: executable_advice_block + attach（bundle → direction_full 文本 + 落盘结构）----
# spec §11：可执行建议走 direction_full 文本注入（reflect→REFLECT_INDEX→下轮 agent），
# 复用 1.17.0 通道，不另造管道。attach 落盘 bundle.paper.executable_advice（含骨架），
# block 把结构压成一行 [实现建议] 文本喂 direction_full。

def test_block_formats_advice_into_direction_text():
    """bundle 带 executable_advice → [实现建议] 文本块（注册名/cfg/可追溯齐全）。"""
    bundle = {"paper": {"executable_advice": _advice()}}
    block = executable_advice_block(bundle)
    assert block.startswith("[实现建议]")
    assert "FooNet" in block
    assert "MODEL_ARCH=FooNet" in block
    assert "2401.00001" in block


def test_block_empty_when_no_advice():
    """bundle 无 executable_advice → ""（direction_full 不注入空块）。"""
    assert executable_advice_block({"paper": {}}) == ""


def test_block_empty_when_empty_bundle():
    """空 bundle → ""。"""
    assert executable_advice_block({}) == ""


def test_attach_populates_executable_advice_with_skeleton():
    """bundle paper 有方法 → attach 写 executable_advice（advice 结构 + skeleton 代码）。"""
    bundle = {"paper": {
        "method_excerpt": "We propose a residual attention architecture.",
        "hits": [{"title": "FooNet", "arxiv_id": "2401.00001"}]}}
    attach_executable_advice(bundle)
    advice = bundle["paper"]["executable_advice"]
    assert advice is not None
    assert advice["target_slot"] == "B"
    assert advice["skeleton"]["code"]  # 骨架已附，agent 读 bundle 即得


def test_attach_sets_none_when_no_method():
    """无方法/无命中 → attach 写 executable_advice=None（落盘侧据此跳过注入）。"""
    bundle = {"paper": {"method_excerpt": None, "hits": []}}
    attach_executable_advice(bundle)
    assert bundle["paper"]["executable_advice"] is None


def test_block_reads_attached_advice_roundtrip():
    """attach → block 回路：contrastive loss 落 C 槽，block 读出 LOSS=InfoNCE。"""
    bundle = {"paper": {
        "method_excerpt": "contrastive loss for representation learning.",
        "hits": [{"title": "InfoNCE", "arxiv_id": "2402.00002"}]}}
    attach_executable_advice(bundle)
    block = executable_advice_block(bundle)
    assert "[实现建议]" in block
    assert "InfoNCE" in block
    assert "LOSS=InfoNCE" in block


# ---- Slice 5: 闭环集成测（骨架→注册→cfg 解析）----
# spec §4 AC #2/#6 机制层：mock 论文 → attach → exec 骨架进隔离 registry → 注册名解析。
# 证「生成骨架→注册→可选中」链路成立。全 train.py NN_SMOKE=1 smoke 走 sandbox e2e
# （模板仓 workspace 是 stub，无法真训），同 fork-trigger 先例延后。

import types  # noqa: E402


def _exec_skeleton_in_isolated_registry(code: str, registry: str) -> tuple[dict, str]:
    """在隔离命名空间 exec 骨架代码：注入 fake nn + 三个 register_*（写隔离 dict）。

    返回 (该 registry 的隔离 dict, 注册的类名) — 模拟 workspace/__init__.py 的注册语义
    而不依赖 torch（保持测试纯快）。
    """
    regs = {"learner": {}, "objective": {}, "augmentation": {}}

    def _make_deco(slot):
        def deco(name):
            def wrap(cls):
                regs[slot][name] = cls
                return cls
            return wrap
        return deco

    ns = {
        "nn": types.SimpleNamespace(Module=object),  # learner/objective 子类基
        "register_learner": _make_deco("learner"),
        "register_objective": _make_deco("objective"),
        "register_augmentation": _make_deco("augmentation"),
    }
    exec(code, ns)  # 装饰器在定义期注册（不触发 __init__/from_cfg 的 NotImplementedError）
    return regs[registry], code


def test_end_to_end_arch_bundle_to_registered_learner():
    """B 槽：arch 论文 → 骨架 exec 进隔离 registry → FooNet 注册 + cfg MODEL_ARCH=FooNet 解析。"""
    bundle = {"paper": {
        "method_excerpt": "We propose FooNet, a residual attention architecture.",
        "hits": [{"title": "FooNet", "arxiv_id": "2401.00001"}]}}
    attach_executable_advice(bundle)
    advice = bundle["paper"]["executable_advice"]
    assert advice is not None and advice["target_registry_slot"] == "learner"

    reg, _ = _exec_skeleton_in_isolated_registry(advice["skeleton"]["code"], "learner")
    name = advice["cfg_mapping"]["MODEL_ARCH"]
    assert name in reg  # 注册成功（AC #2）
    assert reg[name].__name__ == advice["skeleton"]["class_name"]
    # cfg 解析：cfg["MODEL_ARCH"]=name 能在 registry 命中（AC #6 机制层）
    assert reg[name] is not None


def test_end_to_end_loss_bundle_to_registered_objective():
    """C 槽：contrastive loss 论文 → InfoNCE 注册进 objective registry + cfg LOSS 解析。"""
    bundle = {"paper": {
        "method_excerpt": "We introduce a contrastive loss for representation learning.",
        "hits": [{"title": "InfoNCE", "arxiv_id": "2402.00002"}]}}
    attach_executable_advice(bundle)
    advice = bundle["paper"]["executable_advice"]
    assert advice["target_registry_slot"] == "objective"
    reg, _ = _exec_skeleton_in_isolated_registry(advice["skeleton"]["code"], "objective")
    assert advice["cfg_mapping"]["LOSS"] in reg


def test_end_to_end_aug_bundle_to_registered_augmentation():
    """D 槽：mixup augmentation 论文 → MixupAug 注册进 augmentation registry + cfg AUGMENTATION 解析。"""
    bundle = {"paper": {
        "method_excerpt": "A data augmentation pipeline using mixup and cutmix transforms.",
        "hits": [{"title": "MixupAug", "arxiv_id": "2403.00003"}]}}
    attach_executable_advice(bundle)
    advice = bundle["paper"]["executable_advice"]
    assert advice["target_registry_slot"] == "augmentation"
    reg, _ = _exec_skeleton_in_isolated_registry(advice["skeleton"]["code"], "augmentation")
    assert advice["cfg_mapping"]["AUGMENTATION"] in reg


def test_end_to_end_empty_bundle_skips_skeleton():
    """无方法/无命中 → executable_advice=None，无骨架生成（不污染 registry）。"""
    bundle = {"paper": {"method_excerpt": None, "hits": []}}
    attach_executable_advice(bundle)
    assert bundle["paper"]["executable_advice"] is None
    assert executable_advice_block(bundle) == ""  # direction_full 不注入


# A2 skeleton_queue tests (appended)
import json
import os
import tempfile
from pathlib import Path
from unittest.mock import patch

from scripts.lib.external import executable_advice as ea


def test_skeleton_queue_write_pending(tmp_path, monkeypatch):
    """A2: attach_executable_advice 末尾若 skeleton 非空 → 写 saved/skeleton_queue.json 含 pending_fill。"""
    monkeypatch.chdir(tmp_path)
    saved = tmp_path / "saved"
    saved.mkdir()
    (saved / "skeleton_queue.json").write_text(json.dumps({"v": 1, "items": []}))

    bundle = {
        "v": 1,
        "reflect_id": "R20260716_001",
        "round": 5,
        "paper": {
            "executable_advice": {
                "skeleton": {
                    "registry": "learner",
                    "registry_name": "Poly",
                    "class_name": "Poly",
                    "code": "@register_learner('Poly')\nclass Poly(nn.Module):\n    def __init__(self, cfg=None): raise NotImplementedError('skeleton')\n",
                },
                "paper_ref": "arxiv:2503.10594",
            }
        },
    }
    with patch.object(ea, "_resolve_saved_dir", return_value=str(saved)):
        ea.attach_executable_advice(bundle)

    q = json.loads((saved / "skeleton_queue.json").read_text())
    assert len(q["items"]) == 1
    item = q["items"][0]
    assert item["registry_name"] == "Poly"
    assert item["status"] == "pending_fill"
    assert item["round"] == 5
    assert item["deadline_round"] == 7  # current_round + 2
    assert item["paper_ref"] == "arxiv:2503.10594"
    assert "skeleton_signature" in item  # sha256 of code[:200]


def test_skeleton_queue_promote_filled(tmp_path, monkeypatch):
    """A2: 队列里有 pending_fill,业务仓改了 class 实现 → 下一轮 status=filled。"""
    monkeypatch.chdir(tmp_path)
    saved = tmp_path / "saved"
    saved.mkdir()

    pre_q = {
        "v": 1,
        "items": [{
            "id": "R20260715_001-Poly",
            "round": 5,
            "deadline_round": 7,
            "status": "pending_fill",
            "paper_ref": "arxiv:2503.10594",
            "registry": "learner",
            "registry_name": "Poly",
            "class_name": "Poly",
            "skeleton_signature": "abc123def456",
            "created_at": "2026-07-15T00:00:00",
            "filled_round": None,
            "filled_signature": None,
        }],
    }
    (saved / "skeleton_queue.json").write_text(json.dumps(pre_q))

    workspace = tmp_path / "workspace"
    workspace.mkdir()
    impl = workspace / "nn_Learner_Poly.py"
    impl.write_text("# Poly 真实现\nclass Poly(nn.Module):\n    def __init__(self, cfg=None): pass\n")

    bundle = {
        "v": 1,
        "reflect_id": "R20260716_001",
        "round": 6,
        "paper": {"executable_advice": {}},  # 空 → 走 promote 分支
    }
    with patch.object(ea, "_resolve_saved_dir", return_value=str(saved)):
        ea.attach_executable_advice(bundle)

    q = json.loads((saved / "skeleton_queue.json").read_text())
    item = q["items"][0]
    assert item["status"] == "filled"
    assert item["filled_round"] == 6


def test_skeleton_queue_disabled_via_env(tmp_path, monkeypatch):
    """A2: NN_SKELETON_QUEUE_ENABLED=0 → 不写盘。"""
    monkeypatch.chdir(tmp_path)
    saved = tmp_path / "saved"
    saved.mkdir()
    (saved / "skeleton_queue.json").write_text(json.dumps({"v": 1, "items": []}))
    monkeypatch.setenv("NN_SKELETON_QUEUE_ENABLED", "0")

    bundle = {
        "v": 1,
        "reflect_id": "R20260716_001",
        "round": 5,
        "paper": {
            "executable_advice": {
                "skeleton": {
                    "registry": "learner",
                    "registry_name": "Poly",
                    "class_name": "Poly",
                    "code": "raise NotImplementedError('x')",
                },
                "paper_ref": "arxiv:2503.10594",
            }
        },
    }
    with patch.object(ea, "_resolve_saved_dir", return_value=str(saved)):
        ea.attach_executable_advice(bundle)

    q = json.loads((saved / "skeleton_queue.json").read_text())
    assert q["items"] == []  # 没新增
