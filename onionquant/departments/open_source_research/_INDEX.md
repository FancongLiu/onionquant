# 🔍 开源研究院

> **状态**: working | **任务**: — | **完成**: 4 | **进行中**: 0 | **阻塞**: 0 | **更新**: 2026-05-17T12:55

## 部门职责
调研GitHub上所有优质量化开源项目，评估可复用性，给出采纳/改进/自研建议。

## 天才Agent编制
- **首席GitHub侦察兵** — 发现优质项目，追踪Star趋势
- **代码评估师** — 评估代码质量、架构、可维护性
- **集成架构师** — 制定集成方案，多项目融合设计

## 调研清单

### 综合性量化平台
| 项目 | Stars | 语言 | 优势 | 劣势 | 得分 |
|------|-------|------|------|------|------|
| qlib (Microsoft) | ~16k | Python | 完整AI量化平台 | 偏A股 | 🟡 |
| vnpy | ~25k | Python | 国内最流行 | 偏CTA | 🟡 |
| LEAN (QuantConnect) | ~10k | C#/Python | 专业级 | 学习曲线陡 | 🟡 |
| backtrader | ~14k | Python | 易用 | 性能一般 | 🟡 |
| zipline-reloaded | ~4k | Python | 学术友好 | 维护弱 | 🟡 |
| Freqtrade | ~30k | Python | 最活跃 | 偏加密货币 | 🟡 |
| Jesse | ~6k | Python | AI驱动 | 偏加密货币 | 🟡 |

### AI/ML量化专项
| 项目 | Stars | 核心能力 | 得分 |
|------|-------|---------|------|
| FinRL | ~10k | 强化学习交易 | 🟡 |
| FinGPT | ~14k | LLM金融分析 | 🟡 |
| TensorTrade | ~5k | RL交易框架 | 🟡 |

### 数据与分析工具
| 项目 | 用途 | 得分 |
|------|------|------|
| yfinance | 美股数据 | ✅ 已确认使用 |
| OpenBB | 开源Bloomberg | 🟡 |
| alphalens | 因子分析 | 🟡 |
| pyfolio | 组合分析 | 🟡 |
| vectorbt | 向量化回测 | 🟡 |

## 当前任务
- [T002] 开源量化项目GitHub调研（进行中）
- [T010~T013] 逐个深度评估

## 文件清单
- `_INDEX.md` — 本文件
- `project_evaluations/` → 各项目详细评估报告 (待创建)
- `github_knowledge.md` → 知识图谱 (待创建)
