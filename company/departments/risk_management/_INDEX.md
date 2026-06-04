# 🛡️ 风险管理部

> **状态**: done | **任务**: T854 | **完成**: 8 | **进行中**: 0 | **阻塞**: 0 | **更新**: 2026-05-17T12:55

## 部门职责
风险模型、组合优化、压力测试。确保在任何市场环境下控制回撤。

## 天才Agent编制
- **风控建模师** — VaR/ES/GARCH风险模型
- **组合优化师** — Black-Litterman、Risk Parity、Kelly
- **压力测试专家** — 历史情景、蒙特卡洛模拟

## 技术路线
| 方法 | 复杂度 | 效果 | 适用场景 |
|------|--------|------|---------|
| VaR (方差-协方差) | ⭐ | ⭐⭐ | 快速估算 |
| CVaR/ES | ⭐⭐ | ⭐⭐⭐ | 厚尾分布 |
| GARCH族模型 | ⭐⭐⭐ | ⭐⭐⭐ | 波动率预测 |
| Black-Litterman | ⭐⭐⭐ | ⭐⭐⭐⭐ | 观点融入 |
| Risk Parity | ⭐⭐ | ⭐⭐⭐ | 均衡配置 |
| Kelly Criterion | ⭐⭐ | ⭐⭐⭐ | 仓位管理 |
| 蒙特卡洛模拟 | ⭐⭐⭐ | ⭐⭐⭐⭐ | 前瞻分析 |
| Copula | ⭐⭐⭐⭐ | ⭐⭐⭐ | 尾部依赖 |

## 当前任务
- [T854] 行业中性化与风险归因 ✅ — industry_attribution.py 行业暴露+Barra归因+风险预算
- [T844] 业绩归因分析模块 ✅
- [T843] 压力测试与情景分析 ✅

## 文件清单
- `_INDEX.md` — 本文件
- `risk_metrics.py` — VaR/CVaR/最大回撤/夏普比率
- `portfolio_optimizer.py` — 均值方差/Risk Parity/Kelly
- `drawdown_control.py` — CPPI/波动率目标/止损
- `stress_testing.py` — 8历史危机情景/压力评分
- `performance_attribution.py` — 因子回归/滚动归因/Brinson归因
- `covariance.py` — Ledoit-Wolf/OAS/EW/Factor-Model/RobustMCD协方差估计
- `__init__.py` — 模块导出
- `risk_knowledge.md` → 知识图谱 (待创建)
