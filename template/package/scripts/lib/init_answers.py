"""答案清单（init --answers）：题库加载 / 人话键解析 / 校验归一 / 锁渲染 / 题序 / INFO_PERM 投影。

题库真源：docs/init/init-question-registry.yaml（随 governance-sync Init 组下发）。

运行时（train / auto-run / doctor）不 import 本模块；只有立项技能与 scripts/init_answers.py 用。
"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

try:
    import yaml
except ImportError:  # pragma: no cover
    yaml = None  # type: ignore

REGISTRY_REL = Path("docs") / "init" / "init-question-registry.yaml"
RESOLVED_REL = Path(".auto-nn") / "init-answers.resolved.json"
EXPORT_REL = Path(".auto-nn") / "init-answers.yaml"
SUPPORTED_VERSIONS = (1,)
ANSWERS_SOURCE_TAG = "（来自清单）"
_NONE_WORDS = {"", "none", "null", "暂不设", "不设", "无", "n/a", "na"}
_SKIP_EXPORT_SLUGS = frozenset({"F1-contract", "stage-0-compare"})
_SOURCE_PREFIX = re.compile(r"^（来自清单[^）]*）")
_FIELD_IN_LOCK = re.compile(r"\{([a-zA-Z_][a-zA-Z0-9_]*)\}")
_GUESS_WORDS = {"guessed", "guess", "uncertain", "低"}


class AnswersError(ValueError):
    """题库或清单结构性错误（文件读不了 / 版本不支持 / workflow 非法）。"""


# ── 题库 ────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class Question:
    slug: str
    key: str
    aliases: tuple[str, ...]
    theme: str
    entries: tuple[str, ...]
    step: dict[str, int]
    depends_on: tuple[str, ...]
    source_aligned: bool
    skip_allowed: bool
    skip_reason: str
    kind: str | None
    options: dict[str, dict[str, Any]]
    fields: dict[str, dict[str, Any]]
    lock: str | None
    ask: str

    def option_for(self, raw: Any) -> str | None:
        """字母 / 选项 value / 选项键 → 规范选项键；找不到返回 None。"""
        if raw is None:
            return None
        text = str(raw).strip()
        if not text:
            return None
        for key in self.options:
            if text.lower() == key.lower():
                return key
        for key, opt in self.options.items():
            if str(opt.get("value", "")).lower() == text.lower():
                return key
        return None


@dataclass
class Registry:
    version: int
    entry_by_workflow: dict[str, str]
    questions: list[Question]
    contradictions: dict[str, str]
    path: Path | None = None

    def by_slug(self, slug: str) -> Question | None:
        for q in self.questions:
            if q.slug == slug:
                return q
        return None

    def find(self, key: str) -> Question | None:
        """人话键 / slug / 别名 / slug 前缀（I1）→ 题；大小写、空格、连字符不敏感。"""
        norm = _norm(key)
        for q in self.questions:
            if norm in {_norm(q.slug), _norm(q.key), *(_norm(a) for a in q.aliases)}:
                return q
        for q in self.questions:
            if norm == _norm(q.slug.split("-", 1)[0]):
                return q
        return None

    def entry_for(self, workflow: str) -> str:
        entry = self.entry_by_workflow.get(workflow)
        if entry is None:
            raise AnswersError(f"workflow 须为 {'/'.join(self.entry_by_workflow)}，得到 {workflow!r}")
        return entry

    def skippable(self, entry: str) -> list[Question]:
        return [q for q in self.questions if q.skip_allowed and entry in q.entries]


def _norm(s: str) -> str:
    return re.sub(r"[\s_\-/／]+", "", str(s)).lower()


def default_registry_path() -> Path:
    """<package root>/docs/init/init-question-registry.yaml（本文件在 <root>/scripts/lib/）。"""
    return Path(__file__).resolve().parents[2] / REGISTRY_REL


def load_registry(path: str | Path | None = None) -> Registry:
    if yaml is None:  # pragma: no cover
        raise AnswersError("PyYAML required for init-question-registry")
    p = Path(path) if path else default_registry_path()
    if not p.is_file():
        raise AnswersError(f"题库缺失：{p}")
    data = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
    version = int(data.get("version", 0))
    if version not in SUPPORTED_VERSIONS:
        raise AnswersError(f"题库 version={version} 不支持（支持 {SUPPORTED_VERSIONS}）")
    questions: list[Question] = []
    seen: set[str] = set()
    for raw in data.get("questions") or []:
        slug = str(raw["slug"])
        if slug in seen:
            raise AnswersError(f"题库 slug 重复：{slug}")
        seen.add(slug)
        answers = raw.get("answers") or {}
        questions.append(
            Question(
                slug=slug,
                key=str(raw.get("key") or slug),
                aliases=tuple(str(a) for a in (raw.get("aliases") or [])),
                theme=str(raw.get("theme") or ""),
                entries=tuple(str(e) for e in (raw.get("entries") or [])),
                step={str(k): int(v) for k, v in (raw.get("step") or {}).items()},
                depends_on=tuple(str(d) for d in (raw.get("depends_on") or [])),
                source_aligned=bool(raw.get("source_aligned", False)),
                skip_allowed=bool(answers.get("skip_allowed", False)),
                skip_reason=str(answers.get("reason") or ""),
                kind=raw.get("kind"),
                options={str(k): dict(v or {}) for k, v in (raw.get("options") or {}).items()},
                fields={str(k): dict(v or {}) for k, v in (raw.get("fields") or {}).items()},
                lock=raw.get("lock"),
                ask=str(raw.get("ask") or ""),
            )
        )
    contradictions = {str(c["id"]): str(c.get("message", "")) for c in (data.get("contradictions") or [])}
    return Registry(
        version=version,
        entry_by_workflow={str(k): str(v) for k, v in (data.get("entry_by_workflow") or {}).items()},
        questions=questions,
        contradictions=contradictions,
        path=p,
    )


def steps_for(registry: Registry, workflow: str) -> list[str]:
    """该 workflow 的计步题序（不含准备步 P0 与签字 F1）。update 无步号 → 空列表。"""
    entry = registry.entry_for(workflow)
    numbered = [(q.step[entry], q.slug) for q in registry.questions if entry in q.step and q.step[entry] > 0]
    return [slug for _, slug in sorted(numbered)]


# ── 清单 ────────────────────────────────────────────────────────────────


def load_answers_file(path: str | Path) -> dict[str, Any]:
    if yaml is None:  # pragma: no cover
        raise AnswersError("PyYAML required for answers file")
    p = Path(path)
    if not p.is_file():
        raise AnswersError(f"答案清单不存在：{p}")
    data = yaml.safe_load(p.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise AnswersError(
            f"这不是标准答卷（像是 md/txt 草稿）。先按问卷填成 YAML 再校验：{p}"
        )
    return data


def peek_answers_kind(path: str | Path) -> str:
    """文件是标准答卷（version+answers）还是草稿（md/txt/作文）。缺文件抛 AnswersError。"""
    p = Path(path)
    if not p.is_file():
        raise AnswersError(f"答案清单不存在：{p}")
    try:
        data = yaml.safe_load(p.read_text(encoding="utf-8"))
    except Exception:
        return "draft"
    if isinstance(data, dict) and data.get("version") is not None and isinstance(data.get("answers"), dict):
        return "answers"
    return "draft"


@dataclass
class ResolvedItem:
    slug: str
    key: str
    theme: str
    choice: str | None
    fields: dict[str, Any]
    lock: str
    skip_ui: bool
    confirm_required: bool
    step: int | None
    notes: list[str] = field(default_factory=list)
    guessed: bool = False

    @property
    def user_text(self) -> str:
        """写进 init-qa-log --user 的文字（来源标记 + 选择摘要）。"""
        if self.choice:
            head = f"{ANSWERS_SOURCE_TAG}{self.choice} "
            return (head + self.lock).strip()
        user = str((self.fields or {}).get("user") or "").strip()
        if user:
            return f"{ANSWERS_SOURCE_TAG}{user}"
        return f"{ANSWERS_SOURCE_TAG}{self.lock}".strip()


@dataclass
class Resolved:
    workflow: str
    entry: str
    answers_file: str
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    resolved: dict[str, ResolvedItem] = field(default_factory=dict)
    reference_only: dict[str, Any] = field(default_factory=dict)
    unknown_keys: list[str] = field(default_factory=list)
    info_perm_flags: list[str] = field(default_factory=list)
    confirm_only: bool = False

    @property
    def ok(self) -> bool:
        return not self.errors

    def to_dict(self) -> dict[str, Any]:
        return {
            "version": 1,
            "workflow": self.workflow,
            "entry": self.entry,
            "answers_file": self.answers_file,
            "ok": self.ok,
            "errors": list(self.errors),
            "warnings": list(self.warnings),
            "resolved": {k: {**asdict(v), "user_text": v.user_text} for k, v in self.resolved.items()},
            "reference_only": dict(self.reference_only),
            "unknown_keys": list(self.unknown_keys),
            "info_perm_flags": list(self.info_perm_flags),
            "confirm_only": self.confirm_only,
        }


# ── 字段归一 ────────────────────────────────────────────────────────────


def _is_none_word(v: Any) -> bool:
    return v is None or (isinstance(v, str) and v.strip().lower() in _NONE_WORDS)


def _coerce(name: str, spec: dict[str, Any], raw: Any) -> Any:
    """按 fields[name].type 归一；类型错抛 ValueError。"""
    t = str(spec.get("type") or "str")
    if t == "int":
        if isinstance(raw, bool) or not isinstance(raw, (int, str)):
            raise ValueError(f"{name} 须为整数")
        try:
            v = int(str(raw).strip())
        except ValueError as exc:
            raise ValueError(f"{name} 须为整数") from exc
        if "min" in spec and v < int(spec["min"]):
            raise ValueError(f"{name} 不得小于 {spec['min']}")
        return v
    if t == "number":
        if isinstance(raw, bool) or not isinstance(raw, (int, float, str)):
            raise ValueError(f"{name} 须为数字")
        try:
            return float(raw) if isinstance(raw, str) else raw
        except ValueError as exc:
            raise ValueError(f"{name} 须为数字") from exc
    if t == "number_or_none":
        if _is_none_word(raw):
            return None
        if isinstance(raw, bool) or not isinstance(raw, (int, float, str)):
            raise ValueError(f"{name} 须为数字或 none")
        try:
            return float(raw) if isinstance(raw, str) else raw
        except ValueError as exc:
            raise ValueError(f"{name} 须为数字或 none") from exc
    if t == "str":
        if raw is None:
            return ""
        if isinstance(raw, (list, dict)):
            raise ValueError(f"{name} 须为字符串")
        return str(raw).strip()
    if t == "list":
        if raw is None:
            return []
        if isinstance(raw, str):
            return [s.strip() for s in re.split(r"[;,；，]", raw) if s.strip()]
        if isinstance(raw, (list, tuple)):
            return [str(x).strip() for x in raw if str(x).strip()]
        raise ValueError(f"{name} 须为列表")
    if t == "list_int":
        if raw is None:
            return []
        items = raw if isinstance(raw, (list, tuple)) else re.split(r"[;,；，\s]+", str(raw).strip())
        out: list[int] = []
        for x in items:
            if x == "" or x is None:
                continue
            if isinstance(x, bool) or not isinstance(x, (int, str)):
                raise ValueError(f"{name} 须为整数列表")
            try:
                out.append(int(str(x).strip()))
            except ValueError as exc:
                raise ValueError(f"{name} 须为整数列表") from exc
        return out
    raise ValueError(f"题库字段类型未知：{t}")  # pragma: no cover


def _fmt(v: Any) -> str:
    if v is None:
        return "none"
    if isinstance(v, bool):
        return "yes" if v else "no"
    if isinstance(v, (list, tuple)):
        return ",".join(_fmt(x) for x in v)
    if isinstance(v, float) and v.is_integer():
        return str(int(v))
    return str(v)


def _field_default(spec: dict[str, Any]) -> Any:
    d = spec.get("default")
    t = str(spec.get("type") or "str")
    if d is None:
        if t.startswith("list"):
            return []
        if t == "str":
            return ""
        return None
    if t == "number_or_none" and _is_none_word(d):
        return None
    if t.startswith("list") and not isinstance(d, list):
        return [d]
    return d


def render_lock(question: Question, choice: str | None, fields: dict[str, Any]) -> str:
    """选项/字段 → 锁文本（`I1.CONSUMES=…; …` 形式，可被 lock_normalize 态 1 识别）。"""
    if question.kind == "choice":
        if choice is None or choice not in question.options:
            raise ValueError(f"{question.slug} 选项非法：{choice!r}")
        template = str(question.options[choice].get("lock") or "")
    else:
        template = str(question.lock or "")
    values = {k: _fmt(v) for k, v in fields.items()}
    for k, spec in question.fields.items():
        values.setdefault(k, _fmt(_field_default(spec)))
    try:
        return template.format(**values)
    except KeyError as exc:  # pragma: no cover
        raise ValueError(f"{question.slug} 锁模板缺字段 {exc}") from exc


def _split_guessed(raw: Any) -> tuple[Any, bool]:
    """从一题原始值里抽出 guessed / confidence，不进字段校验。"""
    if not isinstance(raw, dict):
        return raw, False
    body = dict(raw)
    guessed = bool(body.pop("guessed", False))
    conf = str(body.pop("confidence", "") or "").strip().lower()
    if conf in _GUESS_WORDS:
        guessed = True
    return body, guessed


_DATA_LOSS_YES = {"yes", "true", "on", "1", "开"}
_DATA_LOSS_NO = {"no", "false", "off", "0", "关", ""}
_T1_EXTRA_KEYS = frozenset({"user", "note", "lock", "common_try", "data_loss"})


def _parse_data_loss_flag(raw: Any) -> tuple[bool, list[str]]:
    """T1 常见可试 data-loss：yes/true/开 → True；缺省 / no → False。"""
    if raw is None:
        return False, []
    if isinstance(raw, bool):
        return raw, []
    text = str(raw).strip().lower()
    if text in _DATA_LOSS_YES:
        return True, []
    if text in _DATA_LOSS_NO:
        return False, []
    return False, [f"common_try.data_loss 须为 yes/no，得到 {raw!r}"]


def _freeform_answer(question: Question, raw: Any) -> tuple[str | None, dict[str, Any], list[str]]:
    """无选项题：须 user（或 note）+ lock。T1 可附 common_try.data_loss。"""
    if not isinstance(raw, dict):
        return None, {}, [f"{question.key}：须写成映射（user 或 note + lock）"]
    extras = [k for k in raw if k not in _T1_EXTRA_KEYS]
    errors = [f"{question.key}：未知字段 {k}" for k in extras]
    user = str(raw.get("user") or raw.get("note") or "").strip()
    lock = str(raw.get("lock") or "").strip()
    if not lock:
        errors.append(f"{question.key}：须有非空 lock")
    if not user:
        user = lock
    data_loss = False
    if "common_try" in raw:
        ct = raw["common_try"]
        if isinstance(ct, dict):
            flag, ferr = _parse_data_loss_flag(ct.get("data_loss"))
            data_loss, errors = flag, errors + ferr
            extra_ct = [k for k in ct if k != "data_loss"]
            errors.extend(f"{question.key}：common_try 未知字段 {k}" for k in extra_ct)
        else:
            flag, ferr = _parse_data_loss_flag(ct)
            data_loss, errors = flag, errors + ferr
    if "data_loss" in raw:
        flag, ferr = _parse_data_loss_flag(raw.get("data_loss"))
        data_loss, errors = flag, errors + ferr
    return None, {"user": user, "lock": lock, "data_loss": data_loss}, errors


def normalize_answer(question: Question, raw: Any) -> tuple[str | None, dict[str, Any], list[str]]:
    """一题的原始值 → (choice, fields, errors)。支持简写：choice 题裸字母；单必填字段 value 题裸值。"""
    errors: list[str] = []
    if isinstance(raw, dict):
        body = dict(raw)
    elif question.kind == "choice":
        body = {"choice": raw}
    else:
        required = [k for k, s in question.fields.items() if s.get("required")]
        if len(required) == 1:
            body = {required[0]: raw}
        else:
            return None, {}, [f"{question.key}：须写成映射（字段：{', '.join(question.fields)}）"]

    choice: str | None = None
    if question.kind == "choice":
        choice = question.option_for(body.pop("choice", None))
        if choice is None:
            errors.append(f"{question.key}：choice 须为 {'/'.join(question.options)} 之一")
    body.pop("note", None)

    fields: dict[str, Any] = {}
    for name, spec in question.fields.items():
        if name in body:
            try:
                fields[name] = _coerce(name, spec, body.pop(name))
            except ValueError as exc:
                errors.append(f"{question.key}：{exc}")
        elif spec.get("required") and question.kind != "choice":
            errors.append(f"{question.key}：缺必填字段 {name}")
        else:
            fields[name] = _field_default(spec)
    for extra in body:
        errors.append(f"{question.key}：未知字段 {extra}")

    if choice is not None:
        for req in question.options[choice].get("requires") or []:
            v = fields.get(req)
            if v is None or v == "" or v == []:
                errors.append(f"{question.key}：选 {choice} 必须填 {req}")
    return choice, fields, errors


def _contradictions(registry: Registry, items: dict[str, ResolvedItem]) -> list[str]:
    out: list[str] = []
    g1, g2 = items.get("G1-experiment-mode"), items.get("G2-goal-value")
    if g1 and g2 and g1.choice == "E" and g2.fields.get("value") is not None:
        out.append(f"[X-G1G2] {registry.contradictions.get('X-G1G2', '')}")
    o2 = items.get("O2-gpus-parallel")
    if o2:
        gpus, mp = o2.fields.get("gpus") or [], o2.fields.get("max_parallel")
        if gpus and isinstance(mp, int) and mp > len(gpus):
            out.append(f"[X-O2] {registry.contradictions.get('X-O2', '')}（gpus={len(gpus)} 张，max_parallel={mp}）")
    t1, i1 = items.get("T1-loss-layers"), items.get("I1-train-consumes")
    if t1 and i1 and t1.fields.get("data_loss") and i1.choice == "C":
        msg = registry.contradictions.get("C-DL1", "")
        out.append(f"[C-DL1] {msg}" if msg else "[C-DL1] 常见可试 data-loss 开着时训练许用材料不能是不读文件")
    return out


def project_info_perm_flags(items: dict[str, ResolvedItem]) -> list[str]:
    """I1/I2/I3 → scripts/init_info_perm.py write 的参数列表（无 I 题则空）。"""
    flags: list[str] = []
    i1 = items.get("I1-train-consumes")
    if i1 and i1.choice:
        flags += ["--consumes", i1.choice]
        for a in i1.fields.get("eval_only_assets") or []:
            flags += ["--eval-only-assets", str(a)]
        for r in i1.fields.get("eval_only_readers") or []:
            flags += ["--eval-only-readers", str(r)]
        if i1.choice == "C":
            flags.append("--strict-no-train-files")
    i2 = items.get("I2-official-path")
    if i2 and i2.choice:
        flags += ["--official-path", i2.choice]
        if i2.fields.get("impl"):
            flags += ["--official-path-impl", str(i2.fields["impl"])]
        if i2.fields.get("rule"):
            flags += ["--official-path-rule", str(i2.fields["rule"])]
    i3 = items.get("I3-other-info-rules")
    if i3 and i3.choice:
        rules = i3.fields.get("rules") or []
        flags += ["--other-rules", "均无" if i3.choice == "none" or not rules else "；".join(rules)]
        for k in i3.fields.get("train_batch_keys") or []:
            flags += ["--train-batch-keys", str(k)]
    if flags:
        t1 = items.get("T1-loss-layers")
        data_loss = bool(t1.fields.get("data_loss")) if t1 else False
        flags += ["--enforce", "no" if data_loss else "yes"]
    return flags


def validate_answers(registry: Registry, doc: dict[str, Any], *, workflow: str, answers_file: str = "") -> Resolved:
    entry = registry.entry_for(workflow)
    confirm_only = bool(doc.get("confirm_only"))
    res = Resolved(workflow=workflow, entry=entry, answers_file=answers_file, confirm_only=confirm_only)
    version = doc.get("version")
    if version is None:
        res.errors.append("清单缺 version 字段")
    else:
        try:
            ok_version = int(version) in SUPPORTED_VERSIONS
        except (TypeError, ValueError):
            ok_version = False
        if not ok_version:
            res.errors.append(f"清单 version={version!r} 不支持（支持 {SUPPORTED_VERSIONS}）")
    answers = doc.get("answers")
    if not isinstance(answers, dict) or not answers:
        res.errors.append("清单缺 answers 映射或为空")
        return res

    for key, raw in answers.items():
        q = registry.find(str(key))
        if q is None:
            res.unknown_keys.append(str(key))
            res.warnings.append(f"未知键「{key}」：题库无此题，忽略（不整表作废）")
            continue
        if entry not in q.entries:
            res.warnings.append(f"「{key}」（{q.slug}）：{workflow} 入口无此题，忽略")
            continue
        if q.slug == "F1-contract":
            res.warnings.append("口径汇总不可由清单代签，签字仍现场")
            continue
        raw, guessed = _split_guessed(raw)
        if not q.skip_allowed and not confirm_only:
            res.reference_only[q.slug] = raw
            res.warnings.append(
                f"「{key}」（{q.slug}）：v1 不允许清单跳问（{q.skip_reason or '照问'}），值只作参考"
            )
            continue
        if q.kind in ("choice", "value"):
            choice, fields, errs = normalize_answer(q, raw)
            if errs:
                res.errors.extend(errs)
                continue
            lock = render_lock(q, choice, fields)
        else:
            choice, fields, errs = _freeform_answer(q, raw)
            if errs:
                res.errors.extend(errs)
                continue
            lock = str(fields.get("lock") or "")
        confirm_required = (not confirm_only) and workflow == "migrate" and q.source_aligned
        notes: list[str] = []
        if guessed:
            notes.append("草稿标注为猜测，须现场问")
            res.warnings.append(f"「{key}」（{q.slug}）：草稿为猜测，不跳卡")
        if confirm_required:
            notes.append("迁入源对齐题：须出卡片「清单说 X，源项目是 Y」，不得静默跳问")
            res.warnings.append(f"「{key}」（{q.slug}）：迁入源对齐题，清单值须现场改回确认")
        elif confirm_only and workflow == "migrate" and q.source_aligned:
            notes.append("confirm_only：源对齐差异并入签字表，本步不弹卡")
        if q.depends_on:
            notes.append(f"依赖 {', '.join(q.depends_on)} 确认后才套用")
        skip_ui = not confirm_required and not guessed
        res.resolved[q.slug] = ResolvedItem(
            slug=q.slug,
            key=q.key,
            theme=q.theme,
            choice=choice,
            fields=fields,
            lock=lock,
            skip_ui=skip_ui,
            confirm_required=confirm_required,
            step=q.step.get(entry),
            notes=notes,
            guessed=guessed,
        )

    if confirm_only:
        needed = ["P0-project-brief"] + steps_for(registry, workflow)
        missing = [s for s in needed if s not in res.resolved]
        if missing:
            res.errors.append(
                "confirm_only 须覆盖对齐理解 + 全部计步题，缺：" + ", ".join(missing)
            )
        else:
            if any(i.guessed for i in res.resolved.values()):
                res.warnings.append("confirm_only 含猜测题：那些题仍现场问，不能只签字")
            else:
                res.warnings.append("confirm_only：计步题全覆盖，对人只出口径汇总签字")

    res.errors.extend(_contradictions(registry, res.resolved))
    if res.errors:
        for item in res.resolved.values():
            item.skip_ui = False
    res.info_perm_flags = project_info_perm_flags(res.resolved)
    return res


# ── 锁还原 / 从问答记录导出 ────────────────────────────────────────────


def _lock_template_regex(template: str) -> re.Pattern[str]:
    parts: list[str] = []
    last = 0
    for m in _FIELD_IN_LOCK.finditer(template):
        parts.append(re.escape(template[last : m.start()]))
        parts.append(f"(?P<{m.group(1)}>.*?)")
        last = m.end()
    parts.append(re.escape(template[last:]))
    return re.compile("^" + "".join(parts) + "$")


def _coerce_exported_field(spec: dict[str, Any], raw: str) -> Any:
    text = raw.strip()
    t = str(spec.get("type") or "str")
    if t in {"list", "list_int"}:
        if not text:
            return []
        return _coerce("x", spec, text)
    if t == "number_or_none":
        return _coerce("x", spec, text if text else "none")
    return _coerce("x", spec, text)


def invert_lock(question: Question, lock: str) -> tuple[str | None, dict[str, Any]] | None:
    """锁文本 → (choice, fields)；对不上返回 None。"""
    text = (lock or "").strip()
    if not text:
        return None
    if question.kind == "choice":
        for letter, opt in question.options.items():
            tmpl = str(opt.get("lock") or "")
            if not tmpl:
                continue
            if "{" not in tmpl:
                if text == tmpl:
                    return letter, {}
                continue
            m = _lock_template_regex(tmpl).fullmatch(text)
            if not m:
                continue
            fields: dict[str, Any] = {}
            for name, spec in question.fields.items():
                if name in m.groupdict() and m.group(name) is not None:
                    try:
                        fields[name] = _coerce_exported_field(spec, m.group(name))
                    except ValueError:
                        return None
            return letter, fields
        return None
    tmpl = str(question.lock or "")
    if tmpl and "{" in tmpl:
        m = _lock_template_regex(tmpl).fullmatch(text)
        if not m:
            return None
        fields = {}
        for name, spec in question.fields.items():
            if name in m.groupdict() and m.group(name) is not None:
                try:
                    fields[name] = _coerce_exported_field(spec, m.group(name))
                except ValueError:
                    return None
        return None, fields
    return None


def strip_source_tag(user: str) -> str:
    return _SOURCE_PREFIX.sub("", user or "").strip()


def _choice_from_user(question: Question, user: str) -> str | None:
    text = strip_source_tag(user)
    if not text:
        return None
    token = text.split()[0].rstrip(")）:：、,，")
    return question.option_for(token)


def _answer_body_for_export(question: Question, user: str, lock: str) -> dict[str, Any]:
    inverted = invert_lock(question, lock)
    if inverted is not None:
        choice, fields = inverted
        if question.kind == "choice":
            body: dict[str, Any] = {"choice": choice}
            for name, spec in question.fields.items():
                if name in fields and fields[name] not in (None, "", []):
                    default = _field_default(spec)
                    if fields[name] != default:
                        body[name] = fields[name]
                elif name in fields and spec.get("required"):
                    body[name] = fields[name]
            if choice and question.options.get(choice, {}).get("requires"):
                for req in question.options[choice]["requires"]:
                    if req in fields:
                        body[req] = fields[req]
            return body
        if question.kind == "value":
            return dict(fields)
    if question.kind == "choice":
        letter = _choice_from_user(question, user)
        if letter:
            return {"choice": letter, "user": strip_source_tag(user), "lock": lock}
    user_text = strip_source_tag(user) or lock
    return {"user": user_text, "lock": lock}


def export_from_qa_log(
    registry: Registry,
    *,
    qa_text: str,
    workflow: str | None = None,
) -> dict[str, Any]:
    """问答记录 → 可再交的答卷 dict。签字题不导出。"""
    from lib import init_qa_log as QL  # 局部导入：避免脚本路径下循环

    wf = workflow or QL.parse_workflow(qa_text)
    if not wf:
        raise AnswersError("问答记录没有 workflow 元数据，请传 --workflow")
    registry.entry_for(wf)
    latest = QL.latest_by_slug(QL.parse_entries(qa_text))
    answers: dict[str, Any] = {}
    missing: list[str] = []
    needed = ["P0-project-brief"] + steps_for(registry, wf)
    for slug in needed:
        q = registry.by_slug(slug)
        if q is None:
            continue
        entry = latest.get(slug)
        if entry is None:
            missing.append(slug)
            continue
        answers[q.key] = _answer_body_for_export(q, entry.user, entry.lock)
    confirm_only = not missing
    return {
        "version": 1,
        "confirm_only": confirm_only,
        "workflow": wf,
        "exported": True,
        "answers": answers,
        "_missing": missing,
    }


def dump_answers_yaml(doc: dict[str, Any]) -> str:
    if yaml is None:  # pragma: no cover
        raise AnswersError("PyYAML required to dump answers")
    payload = {k: v for k, v in doc.items() if not str(k).startswith("_")}
    header = (
        "# 立项答卷（从问答记录导出；下次 /auto-nn-init --answers 本文件）\n"
        "# 运行时不读。签字不能代签；换项目先看覆盖表。\n"
    )
    return header + yaml.safe_dump(payload, allow_unicode=True, sort_keys=False)


# ── 示例清单 ────────────────────────────────────────────────────────────


def render_template(registry: Registry, workflow: str) -> str:
    entry = registry.entry_for(workflow)
    lines = [
        "# 立项答案清单（人写；只覆盖你已想好的题，其余照常一问一答）",
        f"# workflow={workflow}；键用人话主题，内部编号见注释。写错的键只警告，不整表作废。",
        "version: 1",
        "answers:",
    ]
    for q in sorted(registry.skippable(entry), key=lambda x: x.step.get(entry, 999)):
        lines.append(f"  # {q.slug}（第 {q.step.get(entry, '?')} 步）{('：' + q.ask) if q.ask else ''}")
        if q.kind == "choice":
            for letter, opt in q.options.items():
                req = f"；须填 {', '.join(opt['requires'])}" if opt.get("requires") else ""
                lines.append(f"  #   {letter}) {opt.get('label', '')}{req}")
            lines.append(f"  {q.key}:")
            lines.append(f"    choice: {next(iter(q.options))}")
            for name, spec in q.fields.items():
                lines.append(f"    # {name}: {_yaml_default(spec)}   # {spec.get('help', '')}".rstrip())
        else:
            lines.append(f"  {q.key}:")
            for name, spec in q.fields.items():
                req = "必填" if spec.get("required") else "可选"
                lines.append(f"    {name}: {_yaml_default(spec)}   # {req}；{spec.get('help', spec.get('type', ''))}")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def _yaml_default(spec: dict[str, Any]) -> str:
    d = spec.get("default")
    t = str(spec.get("type") or "")
    if d is None:
        if t.startswith("list"):
            return "[]"
        if t.endswith("or_none"):
            return "none"
        if t in {"int", "number"}:
            return str(spec.get("min", 0))
        return '""'
    if isinstance(d, list):
        return "[" + ", ".join(str(x) for x in d) + "]"
    return str(d)
