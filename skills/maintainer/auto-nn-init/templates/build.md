# BUILD workflow — ABCDE 改码 manual（原 greenfield）

## 1. 对象类型适配
默认对象类型: **code**（自有训练代码 / workspace 可改，全梯度可用）
改码路径梯度: cfg 改值 → 注册制扩展（@register_xxx）→ 改源码 → 不可改（E 档）
路径上限: source（全梯度可用）
场景注记: 从零起手，无历史经验继承；A-routine 优先调 LR/BATCH_SIZE 起手。

## 2. 5×3 改码参考表
<!-- OVERLAY:5x3 -->
| E | **改什么**: 题面（METRIC_KEYS 等评估键）<br>**路径**: 不可改<br>**踩坑**: contract/metrics.py 锁定评估键；场景号在 cfg + F1 清单，不在 contract（PROTOCOL §2.2） | （同 routine，E 档不升深度） | （同 routine，E 档不升深度） |

## 3. 场景陷阱
- 起手就堆 different 结构，未先用 routine 调好超参基线
- 忽略 ledger context key，改的超参没记进可复现上下文
- E 档题面当超参随手改
