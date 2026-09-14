"""Ticket 05 §11 主体闭环：外部证据包 → 可执行建议（论文→注册项→骨架→smoke）。

spec §11 预拍板：bundle 的 paper 段加「可执行建议」结构 ——
method → target_slot (ABCDE B/C/D) → cfg_mapping → 伪代码/骨架。

本模块纯函数（无 IO）：
- build_executable_advice(paper) → 从 method_excerpt 关键词分类落 ABCDE 槽，按槽映射 cfg 键。
- generate_registry_skeleton(advice) → advice → 注册项骨架代码（Slice 2）。
- executable_advice_block(bundle) → 格式化 [实现建议] direction_full 文本块（Slice 3）。

通道语义（spec §4 / ticket 04 Notes）：可执行建议走 **direction_full 文本注入**
（reflect→REFLECT_INDEX→下轮 agent），**不**与 ticket 04 的 evidence_refs/paper_hint
字段注入通道混——两条注入通道语义不同。
"""
from __future__ import annotations

import re
from typing import Any

# ABCDE 槽 → registry 槽 + cfg 键（改码三原则 pluggable：注册项走 config 开关 + registry）。
# B=learner→MODEL_ARCH, C=objective→LOSS, D=augmentation→AUGMENTATION
# （cfg 键经 workspace/__init__.py 的 build_learner/build_objective/build_transforms 强读）。
_SLOT_TABLE: dict[str, dict[str, str]] = {
    "B": {"registry": "learner", "cfg_key": "MODEL_ARCH"},
    "C": {"registry": "objective", "cfg_key": "LOSS"},
    "D": {"registry": "augmentation", "cfg_key": "AUGMENTATION"},
}

# method_excerpt 关键词 → ABCDE 槽。判定优先级 C/D 先于 B（避免 arch 默认吃掉 loss/aug）。
_LOSS_KEYWORDS = (
    "loss", "objective", "cost function", "cross-entropy", "cross entropy",
    "contrastive", "regulariz", "focal", "triplet", "supervised contrastive",
)
_AUG_KEYWORDS = (
    "augment", "data augmentation", "transform", "preprocess",
    "mixup", "cutout", "cutmix", "rand augment", "randaugment",
)

# CamelCase token（从标题/摘要抽模型或方法名作注册键）。
_NAME_RE = re.compile(r"[A-Z][A-Za-z0-9]+")
# proposed_change 截断（防 [实现建议] 块过长撑爆 direction_full）。
_PROPOSED_MAX_CHARS = 200


def _classify_slot(text: str) -> str:
    """合并文本 → ABCDE 槽（C/D 优先，B 兜底）。

    无信号时调用方应先判空（本函数对空串返回兜底 B，故判空责任在 build_*）。
    """
    low = text.lower()
    for kw in _LOSS_KEYWORDS:
        if kw in low:
            return "C"
    for kw in _AUG_KEYWORDS:
        if kw in low:
            return "D"
    return "B"


def _derive_name(text: str) -> str:
    """从标题/摘要抽注册名：首个 CamelCase token；无则首词首字母大写；空串→''。"""
    if not text:
        return ""
    m = _NAME_RE.findall(text)
    if m:
        return m[0]
    parts = text.split()
    if not parts:
        return ""
    first = re.sub(r"[^A-Za-z0-9]", "", parts[0])
    return (first[:1].upper() + first[1:]) if first else ""


def _derive_paper_ref(paper: dict[str, Any], hits: list) -> str:
    """可追溯标识：pdf_arxiv_id > hit.arxiv_id > hit.url > hit.title > 兜底。"""
    aid = str(paper.get("pdf_arxiv_id") or "").strip()
    first = hits[0] if (hits and isinstance(hits[0], dict)) else {}
    if not aid:
        aid = str(first.get("arxiv_id") or "").strip()
    if aid:
        return f"arxiv:{aid}"
    url = str(first.get("url") or "").strip()
    if url:
        return url
    title = str(first.get("title") or "").strip()
    return title or "external-paper"


def build_executable_advice(paper: dict[str, Any]) -> dict[str, Any] | None:
    """bundle 的 paper 段 → 可执行建议 dict（spec §11）。

    纯函数（无 IO）。返回结构：
        {proposed_change, target_slot (B/C/D), target_registry_slot, cfg_mapping, paper_ref}

    分类源：method_excerpt 关键词（其次首命中标题）。method_excerpt 与标题皆空 → None
    （无可执行建议，落盘/注入侧据此跳过）。

    cfg_mapping 按槽取单键（B→MODEL_ARCH / C→LOSS / D→AUGMENTATION），值=注册名
    （供 Slice 2 generate_registry_skeleton 与下轮 agent 设 cfg）。
    """
    if not isinstance(paper, dict):
        return None
    method = str(paper.get("method_excerpt") or "").strip()
    hits = paper.get("hits") or []
    first = hits[0] if (hits and isinstance(hits[0], dict)) else {}
    title = str(first.get("title") or "").strip()

    classify_text = f"{method} {title}".strip()
    if not classify_text:
        return None

    slot = _classify_slot(classify_text)
    meta = _SLOT_TABLE[slot]
    name = _derive_name(title) or _derive_name(method) or "PaperProposal"

    change = method or title
    return {
        "proposed_change": change[:_PROPOSED_MAX_CHARS],
        "target_slot": slot,
        "target_registry_slot": meta["registry"],
        "cfg_mapping": {meta["cfg_key"]: name},
        "paper_ref": _derive_paper_ref(paper, hits),
    }


# registry 槽 → 装饰器名（workspace/__init__.py 定义）。
_REGISTRY_DECORATOR: dict[str, str] = {
    "learner": "register_learner",
    "objective": "register_objective",
    "augmentation": "register_augmentation",
}

# learner/objective 子类 nn.Module（网络/损失）；augmentation 是 transform，plain class。
_NN_BASE_SLOTS = {"learner", "objective"}

# tracer-bullet 骨架模板：最薄可 exec 注册项，agent 选中后填实现 → smoke（spec §11）。
# from_cfg 返回契约：(instance, metadata_dict)（learner/objective）/ (Compose, dict)（aug）。
_LEARNER_SKELETON = '''\
# 自动生成注册项骨架（外部证据 → 主体闭环 spec §11）
# paper_ref: {paper_ref}
# proposed_change: {proposed}
# TODO(agent): 按 proposed_change 填实现（当前 tracer-bullet 占位，from_cfg 抛 NotImplementedError）
@{decorator}("{name}")
class {class_name}(nn.Module):
    """Skeleton from external evidence ({paper_ref}). Fill per proposed_change."""

    def __init__(self, cfg=None):
        super().__init__()
        # TODO(agent): 按 {paper_ref} 定义结构
        raise NotImplementedError("skeleton; fill __init__ per {paper_ref}")

    def forward(self, *args, **kwargs):
        raise NotImplementedError("skeleton; fill forward per {paper_ref}")

    @classmethod
    def from_cfg(cls, cfg, **kwargs):
        # TODO(agent): 按 proposed_change 构造，返回 (instance, metadata_dict)
        raise NotImplementedError("skeleton; fill from_cfg per {paper_ref}")
'''

_AUG_SKELETON = '''\
# 自动生成注册项骨架（外部证据 → 主体闭环 spec §11）
# paper_ref: {paper_ref}
# proposed_change: {proposed}
# TODO(agent): 按 proposed_change 填实现（当前 tracer-bullet 占位）
@{decorator}("{name}")
class {class_name}:
    """Skeleton transform from external evidence ({paper_ref}). Fill per proposed_change."""

    @classmethod
    def from_cfg(cls, cfg, **kwargs):
        # TODO(agent): 返回 (transforms.Compose, metadata_dict)
        raise NotImplementedError("skeleton; fill from_cfg per {paper_ref}")
'''


def _class_name(name: str) -> str:
    """注册键 → 合法 Python 类名（FooNet→FooNet；foo_net→FooNet；非字母数字切段）。"""
    parts = re.split(r"[^A-Za-z0-9]+", name)
    capped = "".join(p[:1].upper() + p[1:] for p in parts if p)
    return capped or "PaperProposal"


def generate_registry_skeleton(advice: dict[str, Any]) -> dict[str, Any]:
    """advice → 注册项骨架 dict（spec §4/§11）。

    纯函数（无 IO）。返回 {registry, registry_name, class_name, code}：
    - code = 可 exec 的注册项骨架（@register_<slot> + TODO 类体），下轮 agent 选中后填充。
    - tracer-bullet：from_cfg/forward 抛 NotImplementedError，质量后补（agent 填 → smoke）。

    learner/objective 子类 nn.Module；augmentation 是 plain class（transform，from_cfg 返 Compose）。
    """
    registry = advice["target_registry_slot"]
    name = next(iter(advice["cfg_mapping"].values()))
    class_name = _class_name(name)
    fields = {
        "decorator": _REGISTRY_DECORATOR[registry],
        "name": name,
        "class_name": class_name,
        "paper_ref": advice.get("paper_ref", ""),
        "proposed": advice.get("proposed_change", ""),
    }
    template = _LEARNER_SKELETON if registry in _NN_BASE_SLOTS else _AUG_SKELETON
    return {
        "registry": registry,
        "registry_name": name,
        "class_name": class_name,
        "code": template.format(**fields),
    }


def attach_executable_advice(bundle: dict[str, Any]) -> dict[str, Any]:
    """bundle 末尾挂可执行建议（spec §11）：paper.method → advice + skeleton。

    reflect_hook 落盘前调用（single chokepoint）：算 advice、附骨架代码、写
    bundle["paper"]["executable_advice"]（None 表示无建议）。返回 bundle（已 mutate）。

    无方法/无命中 → executable_advice=None（落盘侧/注入侧据此跳过，不崩）。
    paper.executable_advice 已有值 → 保留（A2:让 skeleton_queue 写盘能拿到 skeleton）。
    """
    if not isinstance(bundle, dict):
        return bundle
    paper = bundle.setdefault("paper", {})
    existing = paper.get("executable_advice")
    if not existing:
        advice = build_executable_advice(paper)
        if advice is not None:
            advice["skeleton"] = generate_registry_skeleton(advice)
        paper["executable_advice"] = advice
    _write_skeleton_queue(bundle)  # A2: 写 skeleton_queue.json
    return bundle


# A2: skeleton_queue cross-round tracking (saved/skeleton_queue.json)
import hashlib
import json as _json_a2
import os as _os_a2
from datetime import datetime, timezone
from pathlib import Path


_SKELETON_QUEUE_VERSION = 1
_QUEUE_PATH_NAME = "skeleton_queue.json"
_DEADLINE_OFFSET = 2  # current_round + 2
_QUEUE_ENABLED_ENV = "NN_SKELETON_QUEUE_ENABLED"


def _resolve_saved_dir() -> Path:
    """解析 saved 目录:NN_SAVED_DIR env > ./saved。
    测试用 patch.object 替换;运行时业务仓 cwd 之下 saved/。
    """
    override = _os_a2.environ.get("NN_SAVED_DIR")
    if override:
        return Path(override)
    return Path("saved")


def _skeleton_signature(code: str) -> str:
    return hashlib.sha256((code or "")[:200].encode("utf-8")).hexdigest()[:16]


def _load_queue(saved_dir: Path) -> dict:
    p = saved_dir / _QUEUE_PATH_NAME
    if not p.exists():
        return {"v": _SKELETON_QUEUE_VERSION, "items": []}
    try:
        return _json_a2.loads(p.read_text())
    except Exception:
        return {"v": _SKELETON_QUEUE_VERSION, "items": []}


def _save_queue(saved_dir: Path, queue: dict) -> None:
    p = saved_dir / _QUEUE_PATH_NAME
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(".json.tmp")
    tmp.write_text(_json_a2.dumps(queue, indent=2, ensure_ascii=False))
    tmp.replace(p)


def _gc_queue(queue: dict, current_round: int, grace: int = 5) -> dict:
    """把 status=filled/abandoned 超过 grace 轮的 item 移到 archive。"""
    saved_dir = _resolve_saved_dir()
    if not isinstance(saved_dir, Path):
        saved_dir = Path(saved_dir)
    archive_path = saved_dir / "skeleton_queue.archive.json"
    archive = {"v": _SKELETON_QUEUE_VERSION, "items": []}
    if archive_path.exists():
        try:
            archive = _json_a2.loads(archive_path.read_text())
        except Exception:
            pass
    keep = []
    for item in queue.get("items", []):
        if item.get("status") in ("filled", "abandoned") and item.get("filled_round") is not None:
            if current_round - item["filled_round"] >= grace:
                archive["items"].append(item)
                continue
        keep.append(item)
    queue["items"] = keep
    try:
        archive_path.parent.mkdir(parents=True, exist_ok=True)
        archive_path.write_text(_json_a2.dumps(archive, indent=2, ensure_ascii=False))
    except Exception:
        pass
    return queue


def _write_skeleton_queue(bundle: dict, saved_dir: Path | str | None = None) -> None:
    """A2: 把 bundle.paper.executable_advice.skeleton 写入 saved/skeleton_queue.json。

    - NN_SKELETON_QUEUE_ENABLED=0 → 关闭,不写
    - skeleton 非空 → 写 pending_fill (同 id 已存在则更新 round/deadline_round)
    - skeleton 空 + 同 id pending_fill → 比对业务仓 nn_Learner_<class>.py 代码 hash,变了 → 标 filled
    - 每轮末 GC: filled/abandoned 超过 5 轮 → archive
    """
    if _os_a2.environ.get(_QUEUE_ENABLED_ENV) == "0":
        return
    if saved_dir is None:
        saved_dir = _resolve_saved_dir()
    if not isinstance(saved_dir, Path):
        saved_dir = Path(saved_dir)
    queue = _load_queue(saved_dir)

    current_round = bundle.get("round", 0)
    ea_block = bundle.get("paper", {}).get("executable_advice", {}) or {}
    skeleton = ea_block.get("skeleton")
    reflect_id = bundle.get("reflect_id", "R?")

    if skeleton:
        class_name = skeleton.get("class_name") or skeleton.get("registry_name") or "?"
        item_id = f"{reflect_id}-{class_name}"
        sig = _skeleton_signature(skeleton.get("code", ""))
        existing = next((x for x in queue["items"] if x.get("id") == item_id), None)
        now = datetime.now(timezone.utc).isoformat()
        if existing and existing.get("status") == "pending_fill":
            existing.update({
                "round": current_round,
                "deadline_round": current_round + _DEADLINE_OFFSET,
                "created_at": now,
                "filled_round": None,
                "filled_signature": None,
                "skeleton_signature": sig,
            })
        else:
            queue["items"].append({
                "id": item_id,
                "round": current_round,
                "deadline_round": current_round + _DEADLINE_OFFSET,
                "status": "pending_fill",
                "paper_ref": ea_block.get("paper_ref", ""),
                "registry": skeleton.get("registry", ""),
                "registry_name": skeleton.get("registry_name", ""),
                "class_name": class_name,
                "skeleton_signature": sig,
                "created_at": now,
                "filled_round": None,
                "filled_signature": None,
            })
    else:
        # skeleton 空: 检查 pending_fill 是否已被业务仓填上
        for item in queue["items"]:
            if item.get("status") != "pending_fill":
                continue
            class_name = item.get("class_name", "")
            impl_candidates = [
                Path("workspace") / f"nn_Learner_{class_name}.py",
                Path("workspace") / f"nn_Objective_{class_name}.py",
                Path("workspace") / f"nn_Augmentation_{class_name}.py",
            ]
            for impl in impl_candidates:
                if impl.exists():
                    try:
                        current_sig = hashlib.sha256(impl.read_text()[:500].encode("utf-8")).hexdigest()[:16]
                    except Exception:
                        continue
                    if current_sig != item.get("skeleton_signature"):
                        item["status"] = "filled"
                        item["filled_round"] = current_round
                        item["filled_signature"] = current_sig
                    break

    queue = _gc_queue(queue, current_round)
    _save_queue(saved_dir, queue)


def executable_advice_block(bundle: dict[str, Any]) -> str:
    """bundle → [实现建议] direction_full 文本块（spec §11，复用 1.17.0 通道）。

    纯函数（无 IO）。读 bundle["paper"]["executable_advice"]（attach 落盘的结构），
    压成一行喂 direction_full → REFLECT_INDEX → 下轮 agent。无 advice → ""（不注入）。

    通道语义：direction_full 文本注入（区别于 ticket 04 的 evidence_refs/paper_hint 字段注入）。
    """
    paper = (bundle.get("paper") or {}) if isinstance(bundle, dict) else {}
    advice = paper.get("executable_advice")
    if not isinstance(advice, dict) or not advice:
        return ""
    cfg = advice.get("cfg_mapping") or {}
    cfg_str = ", ".join(f"{k}={v}" for k, v in cfg.items()) or "?"
    name = next(iter(cfg.values()), "?")
    registry = advice.get("target_registry_slot", "?")
    paper_ref = advice.get("paper_ref", "")
    proposed = advice.get("proposed_change", "")
    return (
        f'[实现建议] {proposed} → {registry} 槽 '
        f'@register_{registry}("{name}"); cfg {cfg_str}; '
        f"paper {paper_ref}; 骨架见 bundle paper.executable_advice.skeleton"
    )
