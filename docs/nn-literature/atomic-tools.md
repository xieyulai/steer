# auto-nn 原子工具使用说明

> **读者**：维护者、Agent、手跑调试。  
> **体系入口：** [`docs/AUTO-NN-whitepaper.md`](../AUTO-NN-whitepaper.md)  
> **真源**：`template/package/scripts/`（`lib/external/`）。  
> **原则**：脚本为真源；技能与 `reflect.py` 只调用脚本，不重复实现逻辑。  
> **编排**：外部证据由 **`reflect.py` Phase 1.85** 自动跑；**无**单独 `/auto-nn-external` 技能；维护者手跑 `scripts/external_tool.py`。  
> **更新**：2026-06-27（已实现；本文档为 CLI 与 provider 速查）

---

## 1. 两条轨道

```text
论文线（Paper）                    代码线（Code）
─────────────────                  ─────────────────
找 prior art / 摘要 / 原文          判 routine（标准 API/库）
arxiv · openalex · scholar · pdf   local inspect · docs registry · serper site
· github repo（impl_search）       （不用 GitHub 搜 API 名）
```

**不要混用：**

- GitHub **repo 搜索** → 论文线「有没有公开实现」
- **Documents** → 代码线「是不是 PyTorch/torchvision 内置能力」

---

## 2. 环境变量与 token 一览

在项目根或 `source ~/.env` 后生效。

| 变量 | 用途 | 无此变量时 |
|------|------|------------|
| （无） | arXiv、OpenAlex、本地 introspection | 正常使用 |
| `SERPER_API_KEY` | Scholar + 文档 `site:` 搜索 | 两路 Serper **skip**；论文线改 arXiv+OpenAlex |
| `SERPER_KEY` | 部分机器上的别名 | 代码应映射为 `SERPER_API_KEY` |
| `GITHUB_TOKEN` | GitHub repo 搜索 **提限额** | **仍可用**，约 10 次/分钟（认证后约 30 次/分钟） |
| `OPENALEX_MAILTO` | OpenAlex 礼貌池标识 | 可选，默认占位邮箱 |
| `SEMANTIC_SCHOLAR_API_KEY` | Semantic Scholar | 非 P0；无 key 易 429，建议不用 |

**推荐 `~/.env` 示例（勿 commit）：**

```bash
SERPER_KEY=...          # 或 SERPER_API_KEY=...
GITHUB_TOKEN=github_pat_...
OPENALEX_MAILTO=you@example.com
```

**加载：**

```bash
set -a && source ~/.env && set +a
export SERPER_API_KEY="${SERPER_API_KEY:-$SERPER_KEY}"
```

---

## 3. 统一结果约定（规划）

各原子工具返回结构（库/API 层；CLI 打印 json/markdown）：

```json
{
  "provider": "arxiv | openalex | scholar | pdf | github | docs_local | docs_registry | serper_site",
  "status": "ok | skipped | error",
  "skip_reason": "no_key | no_network | binary_missing | rate_limit | disabled",
  "hits": [],
  "excerpt": ""
}
```

- **`skipped` 不是失败**：编排层继续 reflect，Phase 2 禁止引用未出现在 bundle 内的 url。

---

## 4. 论文线工具

### 4.1 arXiv 检索（P1-arxiv）

| 项 | 说明 |
|----|------|
| **状态** | ✅ 已实现（`lib/external/arxiv.py` + `external_tool.py`） |
| **Token** | **不需要** |
| **网络** | 需要 |
| **后端** | `export.arxiv.org/api/query` |

**命令（业务仓 / 模板包根目录）：**

```bash
python3 scripts/external_tool.py arxiv -q "causal physics-informed neural network" --max 5
python3 scripts/external_tool.py arxiv -q "Fourier neural operator" --max 5 --json
python3 scripts/external_tool.py arxiv -q "causal PINN" --max 3
# 兼容旧入口（thin wrapper，同源 lib/external/arxiv.py）：
python3 scripts/literature_search.py -q "causal PINN" --format table --max 3
```

**输出：** `arxiv_id`、`title`、`url`、`published`、`summary`（约 480 字）、`authors`。

| 有/无 token | 行为 |
|-------------|------|
| 任意 | 相同；仅依赖网络 |
| 无网 | `status=skipped`，stderr WARN |

**注意：** 关键词排序 ≠ Scholar canonical 排序；2203.07404 在 causal PINN query 下约为 top3，不一定第 1。

---

### 4.2 OpenAlex（P2-openalex）

| 项 | 说明 |
|----|------|
| **状态** | ✅ CLI `external_tool.py openalex` |
| **Token** | **不需要** |
| **网络** | 需要 |
| **建议** | 请求带 `User-Agent` + `mailto=` |

**手跑（当前可直接 curl / 后续脚本封装）：**

```bash
# 关键词（排序一般，适合探索）
curl -s "https://api.openalex.org/works?search=causal+PINN&per_page=5&mailto=you@example.com"

# 已知 arxiv id → 最稳（推荐）
curl -s "https://api.openalex.org/works/https://doi.org/10.48550/arxiv.2203.07404"

# 精确标题
curl -s "https://api.openalex.org/works?search=Respecting+causality+PINN&per_page=3&mailto=you@example.com"

# year_min（crew 同款）
curl -s "https://api.openalex.org/works?search=causal+PINN&filter=from_publication_date:2022-01-01&per_page=5&mailto=you@example.com"
```

| 有/无 token | 行为 |
|-------------|------|
| 无 OpenAlex key | 正常使用 |
| 无网 | skip |
| 无效 filter（如 `ids.arxiv:`） | HTTP 400 → skip |

**不要用：** `search` + `sort=cited_by_count:desc`（结果易跑题）。  
**不提供：** 全文；可有 `abstract` + `open_access.oa_url`（pdf 链接）。

---

### 4.3 Serper Google Scholar（P3-scholar）

| 项 | 说明 |
|----|------|
| **状态** | 📋 规划；参考 crew_agent `google_scholar_core.py` |
| **Token** | **`SERPER_API_KEY` 必需** |
| **Endpoint** | `POST https://google.serper.dev/scholar` |
| **不是** | arXiv API |

**手跑（有 key 时）：**

```bash
source ~/.env && export SERPER_API_KEY="${SERPER_API_KEY:-$SERPER_KEY}"

python3 - <<'PY'
import json, os, urllib.request
key = os.environ["SERPER_API_KEY"]
req = urllib.request.Request(
    "https://google.serper.dev/scholar",
    data=json.dumps({"q": "causal physics-informed neural network", "num": 5}).encode(),
    headers={"X-API-KEY": key, "Content-Type": "application/json"},
    method="POST",
)
print(json.dumps(json.load(urllib.request.urlopen(req, timeout=30)), indent=2, ensure_ascii=False)[:2000])
PY
```

| 情况 | 行为 |
|------|------|
| **有 SERPER_API_KEY** | 正常；causal PINN 实测 **2203.07404 常排 #1** |
| **无 key** | HTTP 403 → `skipped: no_serper_key`；**不阻断** |
| 无网 | `skipped: no_network` |

**产出：** title、link、snippet、citedBy、publicationInfo。**无原文 PDF 内容**。

---

### 4.4 PDF 节选（P4-pdf）

| 项 | 说明 |
|----|------|
| **状态** | ✅ CLI `external_tool.py pdf --id 2203.07404` |
| **Token** | 不需要 |
| **依赖** | 网络 + 系统 `pdftotext`（poppler） |
| **输入** | `arxiv_id` 或 `https://arxiv.org/pdf/....pdf` |

**手跑（当前）：**

```bash
# 下载需 patience；校验文件尾有 %%EOF
curl -sL --max-time 300 -o /tmp/paper.pdf "https://arxiv.org/pdf/2203.07404.pdf"
pdftotext /tmp/paper.pdf - | head -80
```

| 情况 | 行为 |
|------|------|
| 下载完整 | `pdftotext` 可抽标题/摘要/章节 |
| 超时/截断 | skip → 降级用 arXiv/OpenAlex 摘要 |
| 无 `pdftotext` | `skipped: binary_missing` |
| 无网 | skip |

**触发建议：** 仅 extend/novel + plateau 等门禁；routine 扫参默认不跑。

---

### 4.5 GitHub 公开 repo 搜索（P5-github-impl）

| 项 | 说明 |
|----|------|
| **状态** | ✅ CLI `external_tool.py github -q "causal PINN"` |
| **轨道** | **论文线** `paper.impl_candidates`（找实现仓库） |
| **Endpoint** | `GET /search/repositories` |
| **不做** | `/search/code`（要 token、限额更严、非 P0） |

**手跑：**

```bash
source ~/.env   # GITHUB_TOKEN 可选

curl -s "https://api.github.com/search/repositories?q=causal+PINN&sort=stars&order=desc&per_page=5" \
  -H "Accept: application/vnd.github+json" \
  -H "User-Agent: auto-nn-literature/1.0" \
  -H "Authorization: Bearer ${GITHUB_TOKEN:-}" 
```

| 情况 | 行为 |
|------|------|
| **无 GITHUB_TOKEN** | ✅ 可搜；search 约 **10 req/min** |
| **有 GITHUB_TOKEN** | ✅ 约 **30 req/min**；Fine-grained：**Public Repositories + Metadata Read** 即可 |
| 403 rate limit | `skipped: rate_limit` |
| 无网 | skip |

**Query 建议：**

| 意图 | query 示例 |
|------|------------|
| 因果 PINN 实现 | `causal PINN`（勿硬加 `pytorch`，易偏题） |
| FNO | `Fourier neural operator` |
| 语言过滤 | `physics informed neural network language:python` |

**实测命中：** `PredictiveIntelligenceLab/CausalPINNs`、`neuraloperator/neuraloperator`（Geo-FNO 等）。

---

### 4.6 论文 metadata 里的 code 链接（P6-linked-code）

| 项 | 说明 |
|----|------|
| **状态** | 📋 规划；从 arXiv 摘要/comment 正则抽 GitHub |
| **Token** | 不需要 |

**实测：** 2203.07404、2010.08895 **metadata 无 GitHub**；不能单靠此路径。  
**补位：** 使用 **4.5 impl_search** 或 Scholar 结果中的链接。

---

## 5. 代码线：Documents（routine 文档）

### 5.1 本地 introspection（C1-docs-local）

| 项 | 说明 |
|----|------|
| **状态** | ✅ CLI `external_tool.py docs --symbol CrossEntropyLoss` |
| **Token** | **不需要** |
| **网络** | **不需要** |

**手跑：**

```bash
python3 - <<'PY'
import inspect, torch.nn as nn
print(inspect.signature(nn.CrossEntropyLoss.__init__))
print((nn.CrossEntropyLoss.__doc__ or "").split("\n")[0])
from torchvision import models
print("resnet18:", hasattr(models, "resnet18"))
PY
```

| 情况 | 行为 |
|------|------|
| 库已安装 | 最佳 routine 证据 |
| `timm` 未安装 | skip timm 分支；靠 registry / Serper |
| 无 GPU/无网 | 仍可用 |

---

### 5.2 Docs registry（C2-docs-registry）

| 项 | 说明 |
|----|------|
| **状态** | 📋 规划 `framework_docs_registry.yaml` + HTTP link_only |
| **Token** | 不需要 |
| **网络** | 抓 excerpt 时需要；link_only 可离线存 url |

**规则（实测）：**

| URL | 结果 |
|-----|------|
| `pytorch.org/docs/stable/.../CrossEntropyLoss.html` | JS 跳转壳页，**勿用于 excerpt** |
| `pytorch.org/docs/2.12/.../CrossEntropyLoss.html` | 可抽正文 |
| `docs.pytorch.org/vision/stable/.../resnet18.html` | 正常 |

**P0：** 只输出 **registry url + 标题**；失败仍保留 link。

---

### 5.3 Serper 文档搜索（C3-serper-site）

| 项 | 说明 |
|----|------|
| **状态** | 📋 规划 |
| **Token** | **`SERPER_API_KEY` 必需** |
| **Endpoint** | `POST https://google.serper.dev/search`（**不是** `/scholar`） |

**手跑：**

```bash
source ~/.env && export SERPER_API_KEY="${SERPER_API_KEY:-$SERPER_KEY}"

python3 - <<'PY'
import json, os, urllib.request
payload = {"q": "CrossEntropyLoss site:pytorch.org/docs", "num": 5}
req = urllib.request.Request(
    "https://google.serper.dev/search",
    data=json.dumps(payload).encode(),
    headers={"X-API-KEY": os.environ["SERPER_API_KEY"], "Content-Type": "application/json"},
    method="POST",
)
for it in json.load(urllib.request.urlopen(req, timeout=25)).get("organic", [])[:3]:
    print(it.get("title"), "\n ", it.get("link"), "\n ", (it.get("snippet") or "")[:100], "\n")
PY
```

| 情况 | 行为 |
|------|------|
| 有 key | 动态补 registry 未覆盖的符号 |
| 无 key | skip；仍可用 C1+C2 |
| 无网 | skip |

**禁止：** 用 GitHub repo 搜索代替 API 文档（`CrossEntropyLoss pytorch` → 第三方 wrapper）。

---

## 6. 有无 token 时的推荐组合

### 6.1 论文线（prior art / impl）

| 配置 | 推荐组合 |
|------|----------|
| **零 key** | arXiv + OpenAlex（DOI/标题直查）+ GitHub repo（无 token） |
| **有 SERPER** | **Scholar 主检索** + arXiv 结构化 + OpenAlex 去重/补 abstract |
| **有 SERPER + GITHUB** | 上者 + impl_search 限额更高 |
| **读原文** | 任意配置 + PDF（易失败，optional） |

### 6.2 代码线（routine）

| 配置 | 推荐组合 |
|------|----------|
| **零 key** | **本地 introspection** + registry **link_only** |
| **有 SERPER** | 上者 + `site:pytorch.org/docs` 补页 |
| **GitHub token** | **不参与** routine 文档（仅论文 impl） |

---

## 7. 统一 CLI（与 reflect Phase 1.85 同源）

真源入口 `scripts/external_tool.py`（维护者手跑；**不写** REFLECT_INDEX pending）：

```bash
python3 scripts/external_tool.py arxiv    -q "..."
python3 scripts/external_tool.py openalex -q "..."
python3 scripts/external_tool.py scholar  -q "..."      # 要 SERPER
python3 scripts/external_tool.py pdf      --id 2203.07404
python3 scripts/external_tool.py github   -q "causal PINN"
python3 scripts/external_tool.py docs     --symbol CrossEntropyLoss
python3 scripts/external_tool.py bundle   --dry-run     # 打印 plan JSON，不 HTTP
```

生产编排：`reflect.py` Phase 1.85 读 EXPERIENCE / 门禁 → `build_external_plan` → HTTP → 写 `saved/evidence_bundle.json`（`paper` / `code` 两节）与 `saved/external_plan.json`。

---

## 8. 快速对照表

| 工具 | 轨道 | Token | 无 token | 无网 |
|------|------|-------|----------|------|
| arXiv | 论文 | — | ✅ | skip |
| OpenAlex | 论文 | — | ✅ | skip |
| Serper Scholar | 论文 | **SERPER** | skip | skip |
| PDF | 论文 | — | ✅* | skip |
| GitHub repo | 论文 impl | 可选 | ✅ 限额低 | skip |
| docs local | 代码 | — | ✅ | ✅ |
| docs registry | 代码 | — | ✅ link | link_only |
| Serper site | 代码 | **SERPER** | skip | skip |

\* PDF 需 `pdftotext` + 能下完 arXiv pdf。

---

## 9. 常见错误

| 现象 | 原因 | 处理 |
|------|------|------|
| Scholar 403 | 无 `SERPER_API_KEY` | 映射 `SERPER_KEY` 或 skip |
| OpenAlex 400 | 错误 filter | 改用 DOI 直查 |
| GitHub 403 + remaining=0 | 限额 | 等待或 skip |
| pdftotext xref 错 | PDF 未下完 | 重试 + `%%EOF` 校验 |
| PyTorch stable 页无正文 | JS 跳转 | registry 用 **2.12** 等钉版本 url |
| Phase 2 假 arXiv 链接 | 未走 bundle | 只允许引用 bundle 内 url |

---

## 10. 相关路径

| 路径 | 说明 |
|------|------|
| `template/package/scripts/external_tool.py` | 统一 CLI（维护者手跑） |
| `template/package/scripts/lib/external/` | 原子 provider 库（arxiv / openalex / docs / github 等） |
| `template/package/scripts/literature_search.py` | arXiv 兼容 wrapper（同源 `lib/external/arxiv.py`） |
| `template/package/reflect.py` | Phase 1.85 生产编排 |
| crew_agent `literature/search_core.py` | 多源 Scholar 参考实现 |
| crew_agent `literature/openalex_client.py` | OpenAlex 参考实现 |

---

*接口变更时同步更新本文。*
