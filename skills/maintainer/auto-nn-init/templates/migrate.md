# MIGRATE workflow — ABCDE 改码 manual

## 1. 对象类型适配
默认对象类型: **code**（外部代码迁入 contract；framework 视 decorator 命中可升至 framework）
改码路径梯度: cfg 改值 → 注册制扩展（@register_xxx）→ 改源码 → 不可改（E 档）
路径上限: pattern 二级分流 — port_to_contract 走 register→source，workspace_wrapper 走 source-only
场景注记: 把外部既有项目按 contract 形态迁入，二级分流看 source_root 是另一仓（port_to_contract）还是本地旁挂（workspace_wrapper）；A-routine 优先核 contract/ 边界对齐再动手。

## 2. 5×3 改码参考表
<!-- OVERLAY:5x3 -->
| E | **改什么**: 保留 contract 评估键对接（METRIC_KEYS 等；contract/metrics.py）<br>**路径**: 不可改<br>**踩坑**: 评估键是 contract 一部分，迁入时不动；场景号在 cfg + F1 清单，不在 contract（PROTOCOL §2.2） | （同 routine，E 档不升深度） | （同 routine，E 档不升深度） |

## 3. 场景陷阱
- 迁入时未先核 contract/ 已有 METRIC_KEYS 等评估键、README F1 场景清单，直接重命名覆盖
- port_to_contract 时把外部的 cfg 路径硬塞进 contract 字段
- workspace_wrapper 时把 source_root 与本仓目录结构耦合太紧，后续迁出困难
- E 档题面当超参随手改（contract 锁，迁入不放行）
