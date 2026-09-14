# scripts/init_o3_abcde.py
"""O3 step: write references/manual/abcde-manual.md.

PR2.2: 行为层切换 — 用 detect() 单一入口替代旧的 classify() + _classify_object_type()
双调用。decision tree 简化为 3 workflow × 3 object_type (+ pattern 二级分流 when migrate)。
"""
from __future__ import annotations
import sys
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent / "lib"))
from init_workflow import Workflow, detect

# PR2: 简化 3 object_type → 3 路径上限（cfg→register→source→locked）
_PATH_CEIL = {
    "data": "source",       # 几乎无训练代码（纯数据侧）；路径上限语义保留
    "code": "source",       # 可改源码
    "framework": "register",  # 注册制框架,只能 register 不能改源码
}


def _generate_manual(target_root: Path, workflow: Workflow, object_type: str,
                     templates_dir: Path | str, pattern: str | None = None) -> str:
    """PR2: 接受 Workflow enum + detect() 产出的 object_type/pattern。

    生成 manual markdown：对象类型判定头 + workflow template 表体 + decision_tree 附录。
    来源标注（§3.2 L132）：template 骨架 + 对象分析。源码受限对象类型的 different cell
    标 `_待 reflect 补实_` 让 reflect 补实，不臆造。
    """
    tpl = Path(templates_dir) / f"{workflow.value}.md"  # build.md / migrate.md / update.md
    body = tpl.read_text(encoding="utf-8")
    # 对象类型 overlay：5×3 表体按 object_type 从 overlay/{object_type}.md 取，替换场景模板里的 marker
    marker = "<!-- OVERLAY:5x3 -->"
    if body.count(marker) != 1:
        raise ValueError(
            f"场景模板 {workflow.value}.md 期望恰好 1 个 {marker}，实得 {body.count(marker)}"
        )
    overlay_path = Path(templates_dir) / "overlay" / f"{object_type}.md"
    if not overlay_path.is_file():
        raise FileNotFoundError(
            f"overlay 表缺失: object_type={object_type} -> {overlay_path}"
        )
    overlay_table = overlay_path.read_text(encoding="utf-8").strip()
    if not overlay_table:
        raise ValueError(f"overlay 表为空: {overlay_path}")
    body = body.replace(marker, overlay_table)
    ceil = _PATH_CEIL.get(object_type, "source")
    header = (
        f"<!-- init 生成；对象类型={object_type}；workflow={workflow.value}；"
        f"来源=template 骨架 + 对象分析；路径上限={ceil} -->\n\n"
        f"## 对象类型判定（init）\n\n"
        f"- 识别对象类型: **{object_type}**\n"
        f"- 改码路径上限: {ceil}\n"
    )
    if object_type == "framework":
        header += (
            "- 路径上限=register（禁改源码）。different cell 若穷尽 register/adapter/monkey-patch 仍改不动，"
            "走 fork 触发：agent 单轮内撞墙 → 轮末 reflect 核验 → REFLECT_INDEX 写升级建议 → "
            "下轮 agent 把该 cell 从 register 改 fork（cell 级、单向），照 framework 档 fork 兜底格写法落地。\n"
            "- 优先级：HUMAN_GUIDANCE > manual 路径上限（cell 级；人写「这格必须 fork / 不许动」则无条件听人）。\n"
        )
    header += "\n"
    # WP0.3 撞墙自查清单：从 scenarios/<workflow>.yaml 拼 decision_tree 段，append 到 manual 末尾
    scenario_yaml = (
        Path(__file__).resolve().parent.parent
        / "scenarios" / f"{workflow.value}.yaml"
    )
    appendix = ""
    if scenario_yaml.is_file():
        try:
            sc_data = yaml.safe_load(scenario_yaml.read_text(encoding="utf-8")) or {}
            dt = sc_data.get("decision_tree") or []
            if dt:
                appendix = "\n\n## 撞墙自查清单（WP0.3 scenarios/.yaml decision_tree）\n\n"
                for i, step in enumerate(dt, 1):
                    when = step.get("when", "?")
                    dos = step.get("do") or []
                    appendix += f"### {i}. {when}\n\n"
                    for action in dos:
                        appendix += f"- {action}\n"
                    appendix += "\n"
        except yaml.YAMLError as e:
            print(f"=== 警告: scenarios/{workflow.value}.yaml 解析失败 ({e});跳过 decision_tree 段", file=sys.stderr)
    # PR2: pattern 路由(workflow=migrate 时二级分流 port_to_contract / workspace_wrapper)
    if pattern:
        appendix += f"\n\n## pattern 路由(workflow=migrate 时)\n\n- 本次走 **{pattern}**\n"
    # ③-i：基线 reference 探测段（B-轻，机会式非阻塞，无条件追加到所有 workflow/object_type）
    appendix += (
        "\n\n## 基线 reference 探测（init，机会式、非阻塞）\n\n"
        "本任务是否有**已发表的外部最优 / 标准对照法（reference）**？"
        "机会式判断（非强制，novel 任务常无）：\n"
        "- **读对象仓库本身的代码和说明**——README / docs / 数据集说明 / 代码注释里常写"
        "「对标某论文」「公开最好 X」；你在判定对象类型时本就在读这些，顺手留意有没有公开基准；\n"
        "- **核对测试条件**（须与本仓 `contract.test` / OFFICIAL_TEST / 主指标键可比）："
        "场景协议、数据划分、metric 聚合；**条件不对齐禁止**把论文分写入"
        "`reference_anchor_value` 当上界——应本仓同条件重跑（`baseline_tag=reference`）或请用户给同条件对照；\n"
        "- **读到且条件对齐** → 把最佳指标值 + 来源 + 引用写进 `EXPERIENCE.md`「基线锚点（external reference）」段，"
        "三字段：`reference_anchor_value`（公开最佳指标值，float）/ `reference_source`（本地出处：README 基准段等）/ "
        "`reference_ref`（本地路径或仓库引用的出处）；\n"
        "- **找不到或不对齐** → **请用户给出**方法名 / 发表分+条件 / 或确认 novel；"
        "勿静默当作「无尺子」。用户签字口径以 HARD-GATE **O3-baseline-anchors** 为准"
        "（`saved/baseline_start_intent.json`）。\n"
        "- **推荐起步**：同场景先跑 plain（下界）再跑 reference 方法（对照），再 fancy。\n"
        "写完后每轮 run_context 靶子段会自动显示 reference 行。\n"
        "\n"
        "> **命名铁律**：外部锚点叫 `reference_anchor`（外部/已发表）。"
        "代码里的「SOTA」指**仓内历史最佳**（internal best），不是外部公开参照，勿混。\n"
    )
    return header + body + appendix


def write_init_outputs(
    target_root: Path | str,
    workflow: Workflow,
    object_type: str,
    templates_dir: Path | str,
    pattern: str | None = None,
) -> dict:
    """PR2: write_init_outputs 改签 — 接受 detect() 产出的 workflow/object_type/pattern。

    Generate references/manual/abcde-manual.md. Returns {md_path}.
    """
    repo_root = Path(target_root)
    auto_nn = repo_root / ".auto-nn"
    refs = repo_root / "references"
    auto_nn.mkdir(parents=True, exist_ok=True)
    refs.mkdir(parents=True, exist_ok=True)

    # manual：按 (workflow, 对象类型, pattern) 生成
    manual_dir = refs / "manual"
    manual_dir.mkdir(parents=True, exist_ok=True)
    md_path = manual_dir / "abcde-manual.md"
    md_body = _generate_manual(repo_root, workflow, object_type, templates_dir, pattern)
    md_path.write_text(md_body, encoding="utf-8")

    return {
        "md_path": str(md_path),
    }


def _load_init_align(repo_root: Path) -> dict | None:
    """若存在 .auto-nn/init-align.json 则作为对齐确认真源（优先于裸 detect）。"""
    try:
        from init_align import load_align, validate_align
    except ImportError:
        return None
    data = load_align(Path(repo_root))
    if data is None:
        return None
    validate_align(data)
    return data


def interactive_run(repo_root: Path, source_root: Path | None, templates_dir: Path,
                    force_workflow: str | None = None,
                    framework_hint: dict | None = None,
                    force_object_type: str | None = None) -> dict:
    """v1.33.0 — 增 framework_kind 字段(framework 仓时填;data/code 仓时 None)。

    force_object_type: P0 对齐结论覆盖 detect() 的 object_type（data|code|framework）。
    若存在 init-align.json：workflow/object_type/pattern/framework_name 以其为准
    （CLI force_* 仍可再覆盖，用于 amend 场景）。
    """
    align = _load_init_align(repo_root)
    if align is not None:
        if not force_workflow:
            force_workflow = align.get("workflow")
        if not force_object_type:
            force_object_type = align.get("object_type")
        if framework_hint is None and align.get("framework_name"):
            framework_hint = {
                "name": align.get("framework_name") or "",
                "mutability": align.get("framework_mutability") or "register",
            }
        if source_root is None and align.get("source_root"):
            source_root = Path(align["source_root"])

    result = detect(repo_root, source_root, force_workflow=force_workflow,
                    framework_hint=framework_hint)
    object_type = result.object_type
    if force_object_type:
        if force_object_type not in ("data", "code", "framework"):
            raise ValueError(
                f"未知 --force-object-type={force_object_type!r};"
                f"可选: data, code, framework"
            )
        object_type = force_object_type
    # BUILD 无对齐且无强制时：用 align_probe 建议，避免脚手架误 framework
    if (
        force_object_type is None
        and align is None
        and result.workflow.value == "build"
        and object_type == "framework"
    ):
        try:
            from lib.align_probe import probe as _probe
            sug = _probe(repo_root, source_root, force_workflow=force_workflow)
            object_type = sug.object_type_suggested
        except Exception:
            object_type = "data"
    framework_kind = result.framework_kind if object_type == "framework" else None
    if object_type == "framework" and align and align.get("framework_name"):
        framework_kind = align.get("framework_name")
    pattern = result.pattern
    if align is not None and "pattern" in align:
        pattern = align.get("pattern")
    forced = bool(force_object_type) or align is not None
    print(f"[O3] workflow={result.workflow.value} object_type={object_type}"
          + (f" (align/forced)" if forced else "")
          + (f" pattern={pattern}" if pattern else "")
          + (f" framework_kind={framework_kind}" if framework_kind else ""))
    return {
        "workflow": result.workflow.value,
        "object_type": object_type,
        "pattern": pattern,
        "framework_kind": framework_kind,
        **write_init_outputs(
            target_root=repo_root,
            workflow=result.workflow,
            object_type=object_type,
            templates_dir=templates_dir,
            pattern=pattern,
        ),
    }


if __name__ == "__main__":
    import argparse, json, subprocess, os
    p = argparse.ArgumentParser()
    p.add_argument("--repo-root", required=True)
    p.add_argument("--source-root", default=None)
    p.add_argument("--templates-dir", default="",
                   help="ABCDE 模板目录（v1.28+ 业务仓不再持有 skills/；"
                        "省略则按 $NN_ABCDE_TEMPLATES_DIR > .auto-nn/template-root > <this_file>/.. 解析）")
    p.add_argument("--force-workflow", default=None,
                   help="Skip detect() workflow; build|migrate|update")
    p.add_argument("--force-object-type", default=None,
                   choices=["data", "code", "framework"],
                   help="P0 对齐结论覆盖 detect() object_type; data|code|framework")
    p.add_argument("--framework-name", default=None,
                   help="framework name（agent 看代码判定；命中 framework 时升级 framework 对象类型）")
    p.add_argument("--framework-mutability", default=None,
                   choices=["cfg", "register", "source"],
                   help="改码路径上限信号：cfg|register|source")
    a = p.parse_args()
    framework_hint = None
    if a.framework_name or a.framework_mutability:
        framework_hint = {
            "name": a.framework_name or "",
            "mutability": a.framework_mutability or "cfg",
        }
    # 解析 templates_dir（CLI 层；interactive_run 直接吃 Path）
    repo_root_path = Path(a.repo_root)
    if a.templates_dir:
        tdir = Path(a.templates_dir)
    else:
        env_dir = os.environ.get("NN_ABCDE_TEMPLATES_DIR")
        if env_dir:
            tdir = Path(env_dir)
        else:
            lib = Path(__file__).parent / "lib" / "nn-state.sh"
            tmpl_root = None
            if lib.exists():
                try:
                    out = subprocess.run(
                        ["bash", "-c", f'source "{lib}" && nn_resolve_template_root "{repo_root_path}"'],
                        capture_output=True, text=True, check=False,
                    )
                    if out.returncode == 0 and out.stdout.strip():
                        tmpl_root = Path(out.stdout.strip())
                except OSError:
                    tmpl_root = None
            cand = tmpl_root / "skills/maintainer/auto-nn-init/templates" if tmpl_root else None
            tdir = cand if (cand and cand.is_dir()) else None
            # 维护仓直跑 fallback：仅当祖先路径有 .template-maintainer 标志
            if tdir is None:
                dev_root = Path(__file__).parent.parent.parent
                if (dev_root / ".template-maintainer").exists():
                    cand = dev_root / "skills/maintainer/auto-nn-init/templates"
                    if cand.is_dir():
                        tdir = cand
        if tdir is None or not tdir.is_dir():
            raise SystemExit(f"[init_o3_abcde] 解析失败：未找到 ABCDE 模板目录；"
                             f"显式传 --templates-dir 或设 $NN_ABCDE_TEMPLATES_DIR / "
                             f".auto-nn/template-root")
    out = interactive_run(repo_root_path,
                          Path(a.source_root) if a.source_root else None,
                          tdir,
                          force_workflow=a.force_workflow,
                          framework_hint=framework_hint,
                          force_object_type=a.force_object_type)
    print(json.dumps(out, indent=2))