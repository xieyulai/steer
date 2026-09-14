"""RDDN migrate (T2)：删旧词 extend/novel producer，formal-departure 发 different/derived。

migrate 阶段做迁移 + 收口：旧 extend→derived、旧 novel(formal)→different；
drop_in→derived / substantive→different / 默认→different；novel 留作 dormant 背书槽
（与 different 同档 rank 3，T3 再激活成 L4 attestation）。
"""
from __future__ import annotations

from lib.innovation_fingerprint import (
    _DEPTH_RANK,
    _VALID_DEPTHS,
    _depth_from_change,
    _max_depth,
    apply_novel_ceiling,
    compute_fingerprint_from_configs,
)


# ── 收口：5 个 RDDN 档词被接受，extend 已删 ──────────────────────────────
def test_depth_rank_accepts_five_rddn_values():
    for v in ("ambiguous", "routine", "derived", "different", "novel"):
        assert v in _DEPTH_RANK, f"{v} 应被 _DEPTH_RANK 接受"
        assert v in _VALID_DEPTHS


def test_extend_is_retired_from_depth_rank():
    """contract：旧 extend 词已退役，不再是合法档词。"""
    assert "extend" not in _DEPTH_RANK
    assert "extend" not in _VALID_DEPTHS


def test_rank_rddn_monotonic():
    # routine < derived（部件重排）< different（形式创新）
    assert _DEPTH_RANK["routine"] < _DEPTH_RANK["derived"]
    assert _DEPTH_RANK["derived"] < _DEPTH_RANK["different"]
    # novel 是 dormant 背书槽，T2 阶段与 different 同档（rank 相等，T3 再升 rank 4）
    assert _DEPTH_RANK["different"] == _DEPTH_RANK["novel"]


# ── change token 全部落到 RDDN 档词（contract：不发 extend/novel）─────────
def test_change_tokens_emit_rddn():
    assert _depth_from_change("drop_in") == "derived"      # 旧 extend→derived
    assert _depth_from_change("substantive") == "different"  # 旧 novel→different
    assert _depth_from_change("baseline") == "routine"
    assert _depth_from_change("") == "different"           # 默认不再回落 novel
    assert _depth_from_change("unknown") == "different"


# ── _max_depth 在共存期把 different/novel 视为同档 ──────────────────────────
def test_max_depth_different_and_novel_same_tier():
    assert _max_depth("different", "novel") in ("different", "novel")
    # derived 高于 routine
    assert _max_depth("routine", "derived") == "derived"


# ── contract：多槽/未知键路径发 different（不再回落 novel）──────────────────
def test_multi_slot_change_emits_different():
    """同时改 ≥2 个 primary_key（跨 tier）→ multi_slot → depth=different。"""
    catalog = {
        "primary_keys": {
            "MODEL_ARCH": {"tier": "B", "table": "learners"},
            "LOSS": {"tier": "C", "table": "objectives"},
        },
        "learners": {"x": {"change": "baseline"}},
        "objectives": {"y": {"change": "baseline"}},
        "scalar_keys": [],
    }
    res = compute_fingerprint_from_configs(
        {"MODEL_ARCH": "a", "LOSS": "b"}, {"MODEL_ARCH": "x", "LOSS": "y"}, catalog,
    )
    assert res.depth == "different"
    assert "multi_slot" in res.reasons


def test_unknown_primary_key_emits_different():
    """primary_key 改了但 catalog 无条目 → unknown_key → depth=different。"""
    catalog = {
        "primary_keys": {"LOSS": {"tier": "B", "table": "objectives"}},
        "objectives": {},
        "scalar_keys": [],
    }
    res = compute_fingerprint_from_configs(
        {"LOSS": "ce"}, {"LOSS": "mystery"}, catalog,
    )
    assert res.depth == "different"
    assert "unknown_key" in res.reasons


# ── T3/ADR-2：apply_novel_ceiling — different 默认天花板，novel 背书独占 ──────
# acceptance：①P2 stays different ②P3+ supported→novel ③inconclusive/skipped→different
def test_novel_ceiling_p2_supported_stays_different():
    """① innovate=P2 不能达 novel（无 P3 全文证据，ADR-7 阶梯）。"""
    assert apply_novel_ceiling("different", "supported", "P2") == "different"


def test_novel_ceiling_p3_supported_becomes_novel():
    """② aggressive=P3+ 且文献背书 supported → 升 novel。"""
    assert apply_novel_ceiling("different", "supported", "P3") == "novel"
    assert apply_novel_ceiling("different", "supported", "P4") == "novel"


def test_novel_ceiling_inconclusive_or_skipped_stays_different():
    """③ 弱信号（inconclusive/skipped/无证据）→ 留 different（背书独占）。"""
    assert apply_novel_ceiling("different", "inconclusive", "P3") == "different"
    assert apply_novel_ceiling("different", "skipped", "P3") == "different"
    assert apply_novel_ceiling("different", "", "P3") == "different"


def test_novel_ceiling_passthrough_routine_and_derived():
    """novel 只从 different 升：routine/derived 透传，不会被背书抬成 novel。"""
    assert apply_novel_ceiling("routine", "supported", "P3") == "routine"
    assert apply_novel_ceiling("derived", "supported", "P3") == "derived"
    # novel 已是背书层结果，透传不降级
    assert apply_novel_ceiling("novel", "inconclusive", "P2") == "novel"


# ── T6/ADR-4：introspection → depth（可 import 标准件封顶 derived）──────────────
# inspect_symbol（命名空间扫描）结果回灌 depth：agent 用已知 importable 符号（标准件）
# → depth ∈ {routine, derived}，非 different/novel。非 import 技法不压（走 T8 catalog）。
def test_importable_standard_part_caps_depth_at_derived():
    """AC：agent 用已知 importable 符号（标准件）→ 标 routine/derived（非 different/novel）。
    substantive change 本应 different，但 docs_symbols 全可 import（CrossEntropyLoss =
    torch.nn 标准件）→ introspection 封顶 derived。"""
    catalog = {
        "primary_keys": {"LOSS": {"tier": "C", "table": "objectives"}},
        "objectives": {
            "fancy_ce": {
                "change": "substantive",            # 本应判 different
                "docs_symbols": ["CrossEntropyLoss"],  # 标准件（可 import）
            },
        },
        "scalar_keys": [],
    }
    res = compute_fingerprint_from_configs(
        {"LOSS": "ce"}, {"LOSS": "fancy_ce"}, catalog,
    )
    assert res.depth in ("routine", "derived")
    assert res.depth != "different"
    assert "importable_standard_parts" in res.reasons
    # 审计快照入 result（供 innovation_audit.json 持久化）
    snaps = [s for s in res.symbol_introspection if s.get("symbol") == "CrossEntropyLoss"]
    assert snaps and snaps[0].get("source") == "local"


def test_non_importable_symbol_stays_different():
    """反例：substantive change + 非标准件（不可 import）→ 不封顶，留 different。
    证明 introspection 精确——只认可 import 标准件；非 import 技法（走 T8 catalog）不压。"""
    catalog = {
        "primary_keys": {"LOSS": {"tier": "C", "table": "objectives"}},
        "objectives": {
            "custom_research_loss": {
                "change": "substantive",
                "docs_symbols": ["NotARealTorchSymbol"],  # 不可 import
            },
        },
        "scalar_keys": [],
    }
    res = compute_fingerprint_from_configs(
        {"LOSS": "ce"}, {"LOSS": "custom_research_loss"}, catalog,
    )
    assert res.depth == "different"
    snaps = [s for s in res.symbol_introspection if s.get("symbol") == "NotARealTorchSymbol"]
    assert snaps and snaps[0].get("source") == "not_importable"


def test_partial_importable_does_not_cap():
    """部分符号可 import（另一符号非标准件）→ 不封顶：real innovation 含自定义成分。"""
    catalog = {
        "primary_keys": {"LOSS": {"tier": "C", "table": "objectives"}},
        "objectives": {
            "hybrid": {
                "change": "substantive",
                "docs_symbols": ["CrossEntropyLoss", "CustomThing"],
            },
        },
        "scalar_keys": [],
    }
    res = compute_fingerprint_from_configs(
        {"LOSS": "ce"}, {"LOSS": "hybrid"}, catalog,
    )
    assert res.depth == "different"


def test_whitespace_padded_symbol_still_caps():
    """回归：docs_symbols 带尾空格时，call-site 的 all_symbols 与 scan_symbols 同口径
    （都 strip）→ 仍判全标准件 → 封顶 derived。修 call-site 曾用未 strip 的裸名漏判。"""
    catalog = {
        "primary_keys": {"LOSS": {"tier": "C", "table": "objectives"}},
        "objectives": {
            "padded_ce": {
                "change": "substantive",
                "docs_symbols": ["CrossEntropyLoss "],  # 尾空格
            },
        },
        "scalar_keys": [],
    }
    res = compute_fingerprint_from_configs(
        {"LOSS": "ce"}, {"LOSS": "padded_ce"}, catalog,
    )
    assert res.depth in ("routine", "derived")
    assert res.depth != "different"
    assert "importable_standard_parts" in res.reasons


def test_scan_symbols_tolerates_non_importable():
    """AC②维护命名空间表：scan_symbols 逐符号容错——可 import 返 local，不可 import 返
    not_importable，空名跳过；整批扫描不抛。"""
    from lib.external.docs_local import scan_symbols

    out = scan_symbols(["CrossEntropyLoss", "NotARealTorchSymbol", ""])
    assert len(out) == 2
    by_sym = {s["symbol"]: s for s in out}
    assert by_sym["CrossEntropyLoss"]["source"] == "local"
    assert by_sym["CrossEntropyLoss"]["module"] == "torch.nn"
    assert by_sym["NotARealTorchSymbol"]["source"] == "not_importable"


def test_record_symbol_introspection_writes_audit(tmp_path):
    """AC③：扫描到的成员快照写入 saved/innovation_audit.json（可复现审计）。"""
    import json

    from lib.innovation_audit import record_symbol_introspection

    snaps = [{"symbol": "CrossEntropyLoss", "module": "torch.nn",
              "doc_excerpt": "…", "source": "local"}]
    record_symbol_introspection(tmp_path, snaps)
    data = json.loads(
        (tmp_path / "saved" / "innovation_audit.json").read_text(encoding="utf-8")
    )
    assert data["symbol_introspection"][0]["symbol"] == "CrossEntropyLoss"


def test_record_symbol_introspection_preserves_existing(tmp_path):
    """AC③：落盘合并——已有 external_attestation 不被覆盖（符号快照是新字段）。"""
    import json

    from lib.innovation_audit import record_symbol_introspection

    saved = tmp_path / "saved"
    saved.mkdir()
    (saved / "innovation_audit.json").write_text(
        json.dumps({"external_attestation": "supported"}), encoding="utf-8"
    )
    record_symbol_introspection(tmp_path, [{"symbol": "SiLU", "source": "local"}])
    data = json.loads((saved / "innovation_audit.json").read_text(encoding="utf-8"))
    assert data["external_attestation"] == "supported"  # 既存保留
    assert data["symbol_introspection"][0]["symbol"] == "SiLU"


def test_merge_fingerprint_dedupes_symbol_snapshots():
    """多候选合并：symbol_introspection 按 symbol 去重（首个胜出），不丢、不重。"""
    from lib.innovation_fingerprint import (
        InnovationFingerprintResult,
        _merge_fingerprint_results,
    )

    a = InnovationFingerprintResult(depth="derived")
    a.symbol_introspection = [
        {"symbol": "CrossEntropyLoss", "source": "local"},
        {"symbol": "ReLU", "source": "local"},
    ]
    b = InnovationFingerprintResult(depth="derived")
    b.symbol_introspection = [
        {"symbol": "CrossEntropyLoss", "source": "local"},  # 重复
        {"symbol": "SiLU", "source": "local"},
    ]
    merged = _merge_fingerprint_results([a, b])
    syms = [s["symbol"] for s in merged.symbol_introspection]
    assert syms == ["CrossEntropyLoss", "ReLU", "SiLU"]  # 去重保序


# ── T7/ADR-4：routine 部件重排检测 → derived ───────────────────────────────
# catalog 标 change=recombine 的命中条目：docs_symbols 经 T6 introspection 确认
# 全可 import（routine 标准件）→ derived（新组合，非 routine 无变化、非 different
# 形式创新）；recombine 但部件非全 routine → 非真·routine 重排，升 different。
def test_depth_from_change_recognizes_recombine():
    """AC①：_depth_from_change 认 recombine（不只 drop_in）→ derived。"""
    assert _depth_from_change("recombine") == "derived"


def test_recombine_routine_parts_is_derived():
    """AC③：纯 routine 部件新组合 → derived（非 routine、非 different）。
    catalog 声明 change=recombine + docs_symbols=[CrossEntropyLoss]（标准件）→
    introspection 确认 routine → derived + reason routine_recombination。"""
    catalog = {
        "primary_keys": {"LOSS": {"tier": "C", "table": "objectives"}},
        "objectives": {
            "swap_to_mse": {
                "change": "recombine",
                "docs_symbols": ["CrossEntropyLoss"],  # 标准件（可 import）
            },
        },
        "scalar_keys": [],
    }
    res = compute_fingerprint_from_configs(
        {"LOSS": "ce"}, {"LOSS": "swap_to_mse"}, catalog,
    )
    assert res.depth == "derived"
    assert res.depth != "routine"
    assert res.depth != "different"
    assert "routine_recombination" in res.reasons


def test_recombine_non_routine_parts_escalates_different():
    """AC②：recombine 但部件非全 routine（不可 import）→ 非真·routine 重排，
    升 different。证明 detection 依赖 introspection 认 routine 部件——非 routine
    时不给 derived。"""
    catalog = {
        "primary_keys": {"LOSS": {"tier": "C", "table": "objectives"}},
        "objectives": {
            "swap_to_custom": {
                "change": "recombine",
                "docs_symbols": ["NotARealTorchSymbol"],  # 非标准件
            },
        },
        "scalar_keys": [],
    }
    res = compute_fingerprint_from_configs(
        {"LOSS": "ce"}, {"LOSS": "swap_to_custom"}, catalog,
    )
    assert res.depth == "different"
    assert "recombine_non_routine" in res.reasons


# ── T8/ADR-3：overlay 软提示（runtime 软层，不污染 deterministic depth 硬判定）────
# overlay = workspace/innovation_catalog.local.yaml，由 reflect「寻找」反馈边喂（04）。
# 确定性判定器只硬信种子：overlay 命中 config delta 解析到的 (table,key) → 追加软 reason
# overlay_hint:<key>，**不动 depth**（AC3）。覆盖种子命中 + unknown_key 两类。
def test_overlay_soft_hint_on_seed_hit_does_not_change_depth():
    """AC4②+AC3：种子命中（LOSS=focal, drop_in→derived）+ overlay 也有 objectives.focal
    → 追加软 reason overlay_hint:focal，depth 仍是 derived（不被 overlay 抬/压）。"""
    catalog = {
        "primary_keys": {"LOSS": {"tier": "C", "table": "objectives"}},
        "objectives": {"focal": {"change": "drop_in"}},  # 无 docs_symbols → 不触发 T6 封顶
        "scalar_keys": [],
    }
    overlay = {"objectives": {"focal": {"source": "r5", "note": "其实是已知技法"}}}
    res = compute_fingerprint_from_configs(
        {"LOSS": "ce"}, {"LOSS": "focal"}, catalog, overlay=overlay,
    )
    assert res.depth == "derived"  # 硬判定不变
    assert "overlay_hint:focal" in res.reasons  # 软提示落位
    # 无 overlay 时无软提示（对照）
    res_no_ov = compute_fingerprint_from_configs(
        {"LOSS": "ce"}, {"LOSS": "focal"}, catalog,
    )
    assert "overlay_hint:focal" not in res_no_ov.reasons
    assert res_no_ov.depth == "derived"


def test_overlay_soft_hint_on_unknown_key_keeps_different():
    """AC4②（其实是已知技法）：LOSS=mystery 种子无条目（unknown_key→different）+
    overlay 标 objectives.mystery → 软标注 overlay_hint:mystery，depth 仍 different。
    overlay 不把 unknown_key 抬成已知（不污染硬判），只留软痕。"""
    catalog = {
        "primary_keys": {"LOSS": {"tier": "C", "table": "objectives"}},
        "objectives": {},  # 无 mystery 条目 → unknown_key
        "scalar_keys": [],
    }
    overlay = {"objectives": {"mystery": {"source": "r5", "change": "drop_in"}}}
    res = compute_fingerprint_from_configs(
        {"LOSS": "ce"}, {"LOSS": "mystery"}, catalog, overlay=overlay,
    )
    assert res.depth == "different"  # 硬判 different 不被 overlay 改
    assert "unknown_key" in res.reasons
    assert "overlay_hint:mystery" in res.reasons  # 软标注「实为已知技法」


def test_overlay_no_hint_when_table_or_key_mismatch():
    """AC3 反例：overlay 命中别的 (table,key) → 不该给当前 config 软提示。"""
    catalog = {
        "primary_keys": {"LOSS": {"tier": "C", "table": "objectives"}},
        "objectives": {"focal": {"change": "drop_in"}},
        "scalar_keys": [],
    }
    # overlay 只登记 activations.silu，与当前 objectives.focal 无关
    overlay = {"activations": {"silu": {"source": "r5"}}}
    res = compute_fingerprint_from_configs(
        {"LOSS": "ce"}, {"LOSS": "focal"}, catalog, overlay=overlay,
    )
    assert "overlay_hint:focal" not in res.reasons
    assert res.depth == "derived"


def test_overlay_rollback_restores_soft_hint(tmp_path):
    """AC4③：append overlay → 软提示出现；rollback → 软提示消失、depth 全程不变。"""
    from lib.external.catalog import (
        append_catalog_overlay,
        load_innovation_overlay,
        rollback_catalog_overlay,
    )

    catalog = {
        "primary_keys": {"LOSS": {"tier": "C", "table": "objectives"}},
        "objectives": {"focal": {"change": "drop_in"}},
        "scalar_keys": [],
    }
    # ① 无 overlay → 无软提示
    assert load_innovation_overlay(tmp_path) == {}
    res0 = compute_fingerprint_from_configs(
        {"LOSS": "ce"}, {"LOSS": "focal"}, catalog, overlay=load_innovation_overlay(tmp_path),
    )
    assert "overlay_hint:focal" not in res0.reasons
    assert res0.depth == "derived"

    # ② append overlay → 软提示出现、depth 不变
    append_catalog_overlay(
        tmp_path, source="r5", table="objectives", key="focal", entry={"note": "已知技法"},
    )
    res1 = compute_fingerprint_from_configs(
        {"LOSS": "ce"}, {"LOSS": "focal"}, catalog, overlay=load_innovation_overlay(tmp_path),
    )
    assert "overlay_hint:focal" in res1.reasons
    assert res1.depth == "derived"  # depth 仍不变

    # ③ rollback → 软提示消失、depth 不变（恢复初态）
    removed = rollback_catalog_overlay(tmp_path, "r5")
    assert removed == 1
    res2 = compute_fingerprint_from_configs(
        {"LOSS": "ce"}, {"LOSS": "focal"}, catalog, overlay=load_innovation_overlay(tmp_path),
    )
    assert "overlay_hint:focal" not in res2.reasons
    assert res2.depth == "derived"


def test_load_innovation_catalog_seed_only_ignores_local_override(tmp_path):
    """AC3：确定性判定器只硬信种子。workspace/innovation_catalog.local.yaml（overlay）
    不得被 load_innovation_catalog 合并进硬 catalog——否则反馈边会污染 deterministic depth。
    本测造一个 local override 载 bogus 技法，断言 load_innovation_catalog 不含它。"""
    from lib.innovation_fingerprint import load_innovation_catalog

    (tmp_path / "workspace").mkdir()
    (tmp_path / "workspace" / "innovation_catalog.local.yaml").write_text(
        "objectives:\n  bogus_polluter:\n    change: drop_in\n", encoding="utf-8",
    )
    cat = load_innovation_catalog(tmp_path)
    # 种子被读（真 seed 在 scripts/lib/），但 local 的 bogus 不得混入
    assert "bogus_polluter" not in (cat.get("objectives") or {})
    # overlay 应由 load_innovation_overlay 单独读（软层）
    from lib.external.catalog import load_innovation_overlay
    ov = load_innovation_overlay(tmp_path)
    assert "bogus_polluter" in ov.get("objectives", {})  # overlay 确实读到了


# ── 框架键第二真源：contract/framework_binding.yaml innovation 注册段 ──────────
# 框架仓第三方键（如 MAMMOTH_MODEL）登记在 contract（立项期人审、governance-sync
# 不覆盖、运行期 agent 禁改），load_innovation_catalog 合并进硬判定——不用模板发版，
# 也不破 AC3（contract 不是运行期可写区）。种子优先；畸形注册段上抛（静默当未注册
# 会把格子悄悄翻转，比崩更糟）。
def _write_contract_registration(root, innovation_yaml: str) -> None:
    (root / "contract").mkdir(parents=True, exist_ok=True)
    (root / "contract" / "framework_binding.yaml").write_text(
        innovation_yaml, encoding="utf-8",
    )


_MAMMOTH_REGISTRATION = """\
# Framework 接入总表（节选，仅供测试）
version: 1
innovation:
  primary_keys:
    MAMMOTH_MODEL:
      table: mammoth_algorithms
      tier: B
    BUFFER_SIZE:
      table: mammoth_buffers
      tier: D
  tables:
    mammoth_algorithms:
      bic: {change: baseline}
      derpp: {change: drop_in}
    mammoth_buffers:
      "500": {change: baseline}
"""


def test_framework_binding_registration_merges_into_catalog(tmp_path):
    """contract 注册段的 primary_keys/tables 并入硬 catalog，并直接驱动判档。"""
    from lib.innovation_fingerprint import load_innovation_catalog

    _write_contract_registration(tmp_path, _MAMMOTH_REGISTRATION)
    cat = load_innovation_catalog(tmp_path)
    assert cat["primary_keys"]["MAMMOTH_MODEL"]["table"] == "mammoth_algorithms"
    assert cat["mammoth_algorithms"]["derpp"]["change"] == "drop_in"
    res = compute_fingerprint_from_configs(
        {"MAMMOTH_MODEL": "bic", "BUFFER_SIZE": 500},
        {"MAMMOTH_MODEL": "derpp", "BUFFER_SIZE": 500},
        cat,
    )
    assert (res.primary_tier, res.depth) == ("B", "derived")


def test_seed_takes_precedence_over_contract_registration(tmp_path):
    """contract 试图改写种子通用键（MODEL_ARCH）→ 种子优先，不被仓内悄悄覆盖。"""
    from lib.innovation_fingerprint import load_innovation_catalog

    seed_only = load_innovation_catalog(None)
    _write_contract_registration(
        tmp_path,
        "innovation:\n"
        "  primary_keys:\n"
        "    MODEL_ARCH:\n"
        "      table: hijacked_table\n"
        "      tier: E\n"
        "  tables:\n"
        "    objectives:\n"
        "      ce: {change: substantive}\n",
    )
    cat = load_innovation_catalog(tmp_path)
    assert cat["primary_keys"]["MODEL_ARCH"] == seed_only["primary_keys"]["MODEL_ARCH"]
    assert cat["objectives"] == seed_only["objectives"]  # 种子表也不被覆盖


def test_contract_missing_or_without_section_is_noop(tmp_path):
    """非 framework 仓（无 contract / 无 innovation 段）→ no-op，行为与纯种子一致。"""
    from lib.innovation_fingerprint import load_innovation_catalog

    assert "MAMMOTH_MODEL" not in load_innovation_catalog(tmp_path)["primary_keys"]
    _write_contract_registration(tmp_path, "version: 1\ndata:\n  status: unavailable\n  reason: t\n")
    assert "MAMMOTH_MODEL" not in load_innovation_catalog(tmp_path)["primary_keys"]


def test_malformed_innovation_section_raises(tmp_path):
    """注册段畸形 → ValueError 上抛（不静默当未注册，防格子悄悄翻转）。"""
    import pytest

    from lib.innovation_fingerprint import load_innovation_catalog

    _write_contract_registration(tmp_path, "innovation: [not, a, mapping]\n")
    with pytest.raises(ValueError):
        load_innovation_catalog(tmp_path)
    _write_contract_registration(
        tmp_path, "innovation:\n  primary_keys:\n    X: {tier: B}\n"  # 缺 table
    )
    with pytest.raises(ValueError):
        load_innovation_catalog(tmp_path)


def test_repo_root_none_returns_seed_only(tmp_path):
    """repo_root=None → 纯种子，不合并 contract（单测隔离用）。"""
    from lib.innovation_fingerprint import load_innovation_catalog

    _write_contract_registration(tmp_path, _MAMMOTH_REGISTRATION)
    assert "MAMMOTH_MODEL" not in load_innovation_catalog(None)["primary_keys"]
    assert "MAMMOTH_MODEL" in load_innovation_catalog(tmp_path)["primary_keys"]
