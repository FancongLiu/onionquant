---
name: risk-management
description: 风险管理部 — 市场状态评估·压力测试·回撤控制·二元事件风险量化 (risk_threshold_engine + empyrical + Monte Carlo)
---

# 风险管理部 (Risk Management Department)

## 工具栈 (非手搓)

| 工具 | 用途 | 调用方式 |
|------|------|---------|
| `risk_threshold_engine` | 4级风险状态 (LOW/MODERATE/ELEVATED/SEVERE) + 部署建议 | `RiskThresholdEngine().evaluate()` |
| `statsmodels` | 市场状态转移概率矩阵 | `quant_framework/strategies/regime_detector.py` |
| `empyrical` | MaxDD/CVaR/Omega/Stability | `quant_framework/backtest/harness.py` |
| `numpy` | 蒙特卡洛二元事件模拟 | `binary_catalyst_backtest.py` |
| `quant_framework/risk/stress_testing.py` | 极端情景压力测试 | project module |
| `quant_framework/risk/drawdown_control.py` | 动态回撤控制 | project module |

## 当前风险状态 (2026-05-18)

- **risk_threshold_engine**: MODERATE (复合分 45.88) → REDUCED_DCA (减仓25%)
- **statsmodels MS回归**: 横盘震荡 (regime_1 prob 57.4%)
- **宏观压制**: 美伊战争 + US10Y 4.58% + 油价$110
- **二元事件风险**: DXYZ Starship IFT-12 (40% 失败概率, 失败=-35%)

## 触发条件

- `python scripts/binary_catalyst_backtest.py` — 二元事件风险量化
- `python scripts/decision_engine_v2.py` — 包含 RTE 状态评估
- Cron: 每小时跟随 connectivity_guardian 检查风险状态

## 铁律

- 风险状态 SEVERE → 无条件减仓至 ≤30%
- 单个二元事件仓位 ≤ Kelly 建议 × 1.5
- 硬止损不再协商 — 到达即执行
