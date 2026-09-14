| 档\深度 | routine | derived | different |
|---------|---------|--------|-------|
| A | **改什么**: 超参（LR/BATCH_SIZE/weight_decay）<br>**路径**: cfg<br>**踩坑**: 改完核对 ledger context key 同步 | **改什么**: 调度/搜索策略（scheduler/warmup）<br>**路径**: cfg→注册制<br>**踩坑**: scheduler 与 optimizer 绑定，别拆 | **改什么**: AutoML/元学习起手超参<br>**路径**: 注册制<br>**踩坑**: 搜索空间别撞 E 档 metric |
| B | **改什么**: 注册 backbone 进 registry（禁改源码）<br>**路径**: 注册制<br>**踩坑**: 换完验 input shape | **改什么**: 跨系列架构切换<br>**路径**: 注册制优先 + 兜底 fork（runtime 触发）<br>**踩坑**: 参数量/显存爆 | **改什么**: 自研/组合新架构<br>**路径**: 注册制优先（禁改源码；穷尽后兜底 fork，fork 写法见本表 different 列 fork 兜底）<br>**踩坑**: 先小规模 dry-run |
| C | **改什么**: model 内 loss 构造<br>**路径**: 注册制<br>**踩坑**: loss 缩放未对齐 | **改什么**: 多 loss 联合/加权<br>**路径**: 注册制<br>**踩坑**: 权重初始值 | **改什么**: 自研对比/新目标<br>**路径**: 注册制优先 + 兜底 fork（runtime 触发）<br>**踩坑**: 梯度爆炸/消失 |
| D | **改什么**: 标准数据增强<br>**路径**: cfg→注册制<br>**踩坑**: 增强破坏可复现 | **改什么**: 自动增强搜索/组合<br>**路径**: 注册制<br>**踩坑**: 搜索开销 | **改什么**: 生成/自监督扩充<br>**路径**: 注册制优先 + 兜底 fork（runtime 触发）<br>**踩坑**: 生成质量未验 |
> **迁入硬要求**：写 `contract/framework_binding.yaml`（五能力总表：data/train/eval/train_log/checkpoint）。评估节须能对账框架原样主分；见 PROTOCOL §3.0.2b。
> **迁入硬要求**：写 `contract/framework_binding.yaml`（五能力总表：data/train/eval/train_log/checkpoint）。评估节须能对账框架原样主分；见 PROTOCOL §3.0.2b。
