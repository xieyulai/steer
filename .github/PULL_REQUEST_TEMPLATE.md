## What & why · 改了什么、为什么

<!-- One paragraph. Link the issue if there is one. -->

## Layer touched · 动了哪一层

- [ ] `template/package/` (runtime — synced into business projects)
- [ ] `skills/` (agent behaviour / wording)
- [ ] `template/maintainer/` (skeletons / profiles)
- [ ] `docs/` only

## Verification · 验证

- [ ] `python3 -m pytest tests -q` and `python3 -m pytest template/package/scripts/tests -q` green
- [ ] `bash template/package/scripts/check_package_docs_contract.sh` FAIL=0
- [ ] `bash template/package/scripts/check_skill_contract.sh --quiet` FAIL=0
- [ ] Sync rules in `CLAUDE.md` walked (whitepaper; package-docs checklist for runtime code)
- [ ] `CHANGELOG.md` `[Unreleased]` entry added

## Notes for reviewers · 备注
