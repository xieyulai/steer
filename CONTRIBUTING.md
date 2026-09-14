# Contributing to auto-nn

Thanks for your interest. This page explains where things live, how to test, and how a change
becomes a release. 中文说明在每节之后。

## 1. Where the truth lives · 真源在哪

| You want to change… | Edit here | Never edit |
|---|---|---|
| Runtime behaviour of business projects (train / experiment / reflect / auto-run / scripts) | `template/package/` | copies inside any business project |
| A skill's behaviour or wording | `skills/**/SKILL.md` (+ its reference files) | `~/.cursor/skills/*` (they are symlinks) |
| Project skeletons / profiles | `template/maintainer/` | — |
| Whitepaper, glossary, per-skill reference docs | `docs/` (see [`docs/README.md`](docs/README.md)) | — |

`template/package/` is the **single source of truth**: `new-project.sh` and `governance-sync`
copy it into business projects. Root-level `CLAUDE.md` / `nn-config.yaml` are deliberate copies
for this repository only — do not turn them into mirrors.

真源只有一处：`template/package/`。业务仓里的副本、`~/.cursor/skills/` 下的软链都不要直接改。

## 2. Before you open a PR · 提 PR 前

```bash
python3 -m pip install pytest pyyaml numpy torch torchvision  # torch: CPU wheel is enough
python3 -m pytest tests -q                                      # root tests
python3 -m pytest template/package/scripts/tests -q             # package tests (run separately: same filenames)
bash template/package/scripts/check_package_docs_contract.sh  # FAIL=0
bash template/package/scripts/check_skill_contract.sh --quiet # FAIL=0
```

Then walk the two sync rules in [`CLAUDE.md`](CLAUDE.md) (“每次更新必检”): a change to
`template/package/*` usually needs a matching edit in the whitepaper and, for runtime code, a look
at the package-docs checklist; add an entry under `## [Unreleased]` in [`CHANGELOG.md`](CHANGELOG.md).

改了 `template/package/*` → 跑上面的测试与 lint → 按 `CLAUDE.md`「每次更新必检」回看白皮书与
包文档清单 → 在 `CHANGELOG.md` 的 `[Unreleased]` 段记一条。

## 3. Commit & PR style · 提交风格

- Small, self-contained commits; each one should already pass the tests.
- Message: `type(scope): what and why` — types as in `CHANGELOG.md` (`feat`, `fix`, `docs`,
  `refactor`, `test`, `chore`). Chinese or English are both fine; existing history is Chinese.
- One PR = one logical change. Describe what changed, why, and how you verified it.
- Skills talk to humans in **plain language first**; internal codes only in parentheses
  (`.cursor/rules/skills-plain-language.mdc`). Keep that voice in any SKILL.md edit.

## 4. Releases (maintainers) · 发版

`VERSION` + `CHANGELOG.md` follow [SemVer](https://semver.org/) and
[Keep a Changelog](https://keepachangelog.com/). Releases go through `/bump-version`
(`skills/bump-version/`), which runs `template/package/scripts/release-check.sh` — the 7-step gate
(clean tree, valid version, changelog section and date, skill-code contract lint, package docs
contract lint). The gate's own header comment in `release-check.sh` is the authoritative description.

## 5. Reporting issues · 报问题

Use Gitee Issues. For a bug, include: the template version the project was synced to
(`.auto-nn/version` and `.auto-nn/governance-rev` in the business project), the skill you ran,
the agent front-end (Cursor / Claude Code), and the relevant lines from `_runs/` or the doctor report.

## 6. Code of conduct

Be kind, be specific, assume good faith. Harassment of any kind is not tolerated.
