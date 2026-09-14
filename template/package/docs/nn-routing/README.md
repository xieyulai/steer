# NN 技能自然语言路由

业务仓 Agent 入口真源。斜杠命令与自然语言等价；完整表见 [`intent-map.md`](intent-map.md)。

- **维护**：改表只改本目录；经 `governance-sync`（`/auto-nn-update`）下发业务仓。
- **歧义策略 D**：只读（check / analyse / doctor）直进；modify / clear / auto-run 缺对象先澄清；manual-run vs auto-run 看关键词。
