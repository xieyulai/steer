# workspace/scripts/

Agent **临时 / 探路** 脚本放这里（画图、单次 dump、调试某模块）。

## 规则

- 可以 `from workspace.xxx import ...` 或 `from workspace import model`。
- **不要**被 `train.py` import；正式训练入口仍是 `poetry run python train.py`。
- 迭代结束：有用逻辑收进 `workspace/` 子模块并由 `Workspace` 调用；无用则删除。
- 本目录下 `*.py` 默认 **不入库**（见根 `.gitignore`）；本 README 会提交。

## 不要

- 不要在仓库根目录新建 `probe.py`、`debug.py` 等（preflight G-布局 会警告）。
