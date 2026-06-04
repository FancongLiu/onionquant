# 风险管理知识图谱

> 构建日期：2026-05-17
> 用途：风控建模知识库，记录关键概念、关系、算法和工具

---

## 一、知识领域总图

```
风险管理知识体系
├── 风险度量（Risk Metrics）
│   ├── 传统度量
│   │   ├── 波动率（Volatility / Standard Deviation）
│   │   ├── 在险价值（Value at Risk, VaR）
│   │   ├── 条件在险价值（CVaR / Expected Shortfall）
│   │   ├── 最大回撤（Max Drawdown）
│   │   └── 下行标准差（Semi-Deviation）
│   ├── 高级度量
│   │   ├── 熵在险价值（Entropic VaR, EVaR）
│   │   ├── 相对论在险价值（Relativistic VaR, RLVaR）
│   │   ├── Tail Gini
│   │   ├── 尾部依赖性（Tail Dependence）
│   │   └── Ulcer指数
│   ├── 绩效度量
│   │   ├── Sharpe比率
│   │   ├── Sortino比率
│   │   ├── Calmar比率
│   │   ├── Omega比率
│   │   └── 信息比率（Information Ratio）
│   └── 信用风险度量
│       ├── Altman Z-Score
│       ├── 违约概率（PD）
│       └── 违约损失率（LGD）
│
├── 组合优化（Portfolio Optimization）
│   ├── 经典方法
│   │   ├── 均值-方差（MVO / Markowitz）
│   │   ├── 有效前沿（Efficient Frontier）
│   │   └── 最小方差组合（GMV）
│   ├── 贝叶斯方法
│   │   ├── Black-Litterman模型
│   │   └── 收缩估计（Shrinkage）
│   ├── 风险预算方法
│   │   ├── 风险平价（Risk Parity）
│   │   ├── 层次风险平价（HRP）
│   │   ├── 层次等风险贡献（HERC）
│   │   └── 嵌套聚类优化（NCO）
│   ├── 尾部风险优化
│   │   ├── 均值-CVaR优化
│   │   ├── 均值-CDAR（条件回撤）优化
│   │   ├── 均值-EVaR优化
│   │   └── 最坏情况优化（Minimax）
│   └── 新兴方法
│       ├── Tsallis熵优化
│       ├── Mean-Tail Gini
│       ├── 模糊均值-方差-偏度（Fuzzy MVS）
│       └── 鲁棒优化 + 遗传算法
│
├── 波动率建模（Volatility Modeling）
│   ├── GARCH家族
│   │   ├── GARCH(1,1)
│   │   ├── GJR-GARCH（捕获杠杆效应）
│   │   ├── EGARCH（指数GARCH）
│   │   ├── EGARCH-X（含外生变量）
│   │   └── Multivariate GARCH（DCC-GARCH等）
│   ├── 机器学习方法
│   │   ├── XGBoost波动率预测
│   │   ├── LSTM/GRU波动率预测
│   │   └── 集成方法
│   └── 实现方式
│       ├── Python `arch` 包
│       ├── Python `statsmodels`
│       └── 自定义实现（MLE优化）
│
├── 压力测试（Stress Testing）
│   ├── 历史情景
│   │   ├── 2008全球金融危机
│   │   ├── COVID-19疫情冲击
│   │   ├── 2000互联网泡沫
│   │   ├── 1994债券市场崩盘
│   │   ├── 2020年3月流动性危机
│   │   └── 2025关税震荡（Tariff Tantrum）
│   ├── 假设情景
│   │   ├── 利率冲击（加息/降息）
│   │   ├── 权益市场暴跌（-10%/-20%/-30%）
│   │   ├── 信用利差扩大
│   │   ├── 通胀/通缩
│   │   └── 地缘政治事件
│   └── 方法论
│       ├── 因子映射分析
│       ├── 相关性崩溃分析
│       ├── 蒙特卡洛模拟
│       ├── 机器学习加权情景
│       └── Entropy Pooling（熵池法）
│
├── 回撤控制（Drawdown Control）
│   ├── 止损机制
│   │   ├── 最大总回撤限制（15-20%硬止损）
│   │   ├── 每日/周度损失限制
│   │   └── 浮动回撤保护（Trailing DD Stop）
│   ├── 动态风险调整
│   │   ├── 波动率目标化（Volatility Targeting）
│   │   ├── ATR-based仓位管理
│   │   ├── Sigmoid动态分配
│   │   └── VIX/波动率制度过滤器
│   ├── 组合保险
│   │   ├── CPPI（恒定比例组合保险）
│   │   ├── TIPP（时不变组合保护）
│   │   ├── OBPI（期权组合保险）
│   │   └── DPPI（动态比例组合保险）
│   └── 仓位管理
│       ├── 固定比例仓位
│       ├── Kelly准则
│       ├── Optimal f（最优f）
│       └── 组合热度规则（Portfolio Heat Rule）
│
├── 尾部风险对冲（Tail Risk Hedging）
│   ├── 直接对冲
│   │   ├── OTM看跌期权（S&P 500 Put）
│   │   ├── VIX期货/期权
│   │   ├── 尾部风险ETF（CAOS, FAIL）
│   │   └── Universa BSPP协议
│   ├── 间接对冲
│   │   ├── Carry货币对冲（AUD Put）
│   │   ├── 国债对冲
│   │   └── 跨资产相关性对冲
│   └── 执行策略
│       ├── 阶梯式建仓（分散时间和行权价）
│       ├── Carry中性（用其他收益覆盖期权成本）
│       ├── 永久性持续对冲（PIMCO方式）
│       └── 动态调整附件点（Attachment Point）
│
├── Python工具链（Python Toolchain）
│   ├── 核心基础设施
│   │   ├── pandas / numpy / scipy
│   │   ├── cvxpy（凸优化）
│   │   └── yfinance（数据获取）
│   ├── 组合优化
│   │   ├── Riskfolio-Lib（最全面，32+风险度量）
│   │   ├── PyPortfolioOpt（经典，文档好，维护模式）
│   │   ├── skfolio（最新，sklearn兼容）
│   │   └── riskparity（CCD风险平价）
│   ├── 波动率与统计
│   │   ├── arch（GARCH建模）
│   │   ├── statsmodels（时间序列）
│   │   └── scikit-learn / xgboost（ML方法）
│   ├── 机构级系统
│   │   ├── ORE（Open Source Risk Engine，LSEG）
│   │   ├── QuantLib（衍生品定价）
│   │   └── qfinlib（固收/利率）
│   └── 风险管理工具
│       ├── RiskOptima（全栈风控）
│       ├── FinanceToolkit（180+比率）
│       ├── empyrical（轻量级指标）
│       └── financial-risk-analyzer（VaR+Z-Score+压力）
│
└── 2025前沿趋势
    ├── AI/LLM融合风控
    │   ├── LLM-Guided Smart Clustering（ACM ICAIF 2025）
    │   ├── 情绪门控再平衡（Sentiment-based Gating）
    │   └── LLM-Black-Litterman集成（ICLR 2025 workshop）
    ├── 精准对冲
    │   ├── 因子级别对冲取代ETF粗放对冲
    │   └── 优化驱动对冲策略
    ├── 总组合管理（Total Portfolio Approach）
    │   ├── CalPERS TPA模型
    │   └── 按功能分配非按标签分配
    ├── 熵优化范式
    │   ├── Tsallis熵组合优化
    │   └── Mean-Deviation-Entropy三目标模型
    └── 制度检测
        ├── 聚类识别市场状态
        └── 动态适应压力情景生成
```

---

## 二、关键实体关系

### 2.1 风险度量层次关系

```
风险度量
├── 位置度量: 均值、中位数
├── 离散度量: 方差、标准差、MAD
├── 下行风险度量:
│   ├── Semi-Deviation
│   ├── VaR (分位数)
│   ├── CVaR (尾部均值)
│   ├── EVaR (熵上界)
│   ├── RLVaR (相对论熵)
│   └── Tail Gini (尾部基尼系数)
├── 回撤度量:
│   ├── Max Drawdown
│   ├── Average Drawdown
│   ├── Drawdown at Risk (DaR)
│   ├── Conditional DaR (CDaR)
│   └── Ulcer Index
└── 一致性风险度量(Coherent):
    ├─ 次可加性(Sub-additivity) ✓CVaR ✓EVaR ✗VaR
    ├─ 单调性(Monotonicity) ✓所有
    ├─ 正齐次性(Positive Homogeneity) ✓所有
    └─ 平移不变性(Translation Invariance) ✓所有
```

### 2.2 优化方法关系图

```
输入数据
  ├── 收益序列 → MVO, HRP, 熵优化
  ├── 协方差矩阵 → Risk Parity, MVO, MDP
  ├── 市场均衡 → Black-Litterman
  └── 胜率/盈亏比 → Kelly准则

优化方法 → 输出权重
  ├── MVO → 对收益估计极度敏感
  ├── Black-Litterman → 贝叶斯稳定化
  ├── Risk Parity → 无需收益预测
  ├── HRP → 层次结构、对噪声鲁棒
  └── Kelly → 最大化长期增长

权重约束
  ├── 做多/做空限制
  ├── 行业/因子中性
  ├── 换手率限制
  ├── 跟踪误差限制
  └── 杠杆限制
```

### 2.3 风险控制体系

```
市场环境
  ├── 低波动/趋势 → 正常仓位
  ├── 高波动/危机 → 降仓/对冲
  ├── 极端事件 → 止损/保险触发
  └── 制度转换 → 策略切换

防御层
  ├── 第一层: 仓位管理（Kelly / Fixed Fractional）
  ├── 第二层: 止损（硬止损/浮动回撤保护）
  ├── 第三层: 波动率调节（目标波动率）
  ├── 第四层: 尾部对冲（期权/VIX）
  └── 第五层: 组合保险（CPPI/TIPP/OBPI）
```

---

## 三、关键公式备忘

### 3.1 风险度量

**VaR（历史模拟法）：**
```
VaR_α = -Percentile(R, 1-α)
```

**CVaR（期望损失）：**
```
CVaR_α = -E[R | R ≤ -VaR_α]
```

**Cornish-Fisher修正VaR：**
```
z_cf = z_α + (z_α² - 1)·S/6 + (z_α³ - 3·z_α)·K/24 - (2·z_α³ - 5·z_α)·S²/36
VaR_cf = μ + σ · z_cf
```
其中S=偏度, K=超额峰度

**最大回撤：**
```
MaxDD = min_t (V_t / max_{s≤t} V_s - 1)
```

### 3.2 组合优化

**MVO目标函数：**
```
max w'μ - λ/2 · w'Σw
```

**Black-Litterman后验收益：**
```
E[R] = [(τΣ)^(-1) + P'Ω^(-1)P]^(-1) · [(τΣ)^(-1)Π + P'Ω^(-1)Q]
```

**市场隐含收益（逆向优化）：**
```
Π = λ · Σ · w_mkt
```
其中λ = (R_mkt - r_f) / σ²_mkt

**风险平价条件：**
```
w_i · (Σw)_i = w_j · (Σw)_j  for all i,j
```

**Kelly（连续）：**
```
f* = μ / σ²
```

**CPPI：**
```
E_t = M · (V_t - F_t)  where F_t = F₀ · e^(r·t)
```

### 3.3 GARCH(1,1)

```
σ²_t = ω + α · ε²_{t-1} + β · σ²_{t-1}
```
约束: ω > 0, α, β ≥ 0, α + β < 1

**GJR-GARCH（含杠杆）：**
```
σ²_t = ω + α · ε²_{t-1} + γ · I_{t-1} · ε²_{t-1} + β · σ²_{t-1}
```
其中I_{t-1}=1当ε_{t-1}<0

---

## 四、核心库速查

### 4.1 Riskfolio-Lib核心功能

```python
import riskfolio as rp

# 定义组合
port = rp.Portfolio(returns=returns)
port.assets_stats(method_mu='hist', method_cov='hist')

# 优化方法
w = port.optimization(model='MV',           # 可选: MV, CVaR, EVaR, CDaR, etc.
                      rm='MV',              # 风险度量: MV, CVaR, EVaR, MDD, etc.
                      obj='Sharpe',         # 目标: Sharpe, MinRisk, Utility, etc.
                      hist=True)            # 使用历史情景

# 层次风险平价
rp.HCPortfolio(returns=returns).optimization(
    model='HRP',  # or 'HERC', 'NCO'
    linkage='ward',
    codependence='pearson'  # 或 spearman, kendall, mutual_info, tail
)
```

### 4.2 PyPortfolioOpt核心功能

```python
from pypfopt import EfficientFrontier, risk_models, expected_returns

mu = expected_returns.mean_historical_return(prices)
S = risk_models.CovarianceShrinkage(prices).ledoit_wolf()

ef = EfficientFrontier(mu, S)
weights = ef.max_sharpe()  # 或 min_volatility(), efficient_risk(), etc.
ef.portfolio_performance(verbose=True)

# Black-Litterman
from pypfopt import BlackLittermanModel, black_litterman
delta = black_litterman.market_implied_risk_aversion(market_prices)
prior = black_litterman.market_implied_prior_returns(mcaps, delta, S)
bl = BlackLittermanModel(S, pi=prior, absolute_views=views, omega="idzorek")
rets = bl.bl_returns()
```

### 4.3 GARCH建模

```python
from arch import arch_model

# GARCH(1,1)
am = arch_model(returns * 100, vol='Garch', p=1, q=1, dist='normal')
res = am.fit()
forecast = res.forecast(horizon=21)

# GJR-GARCH with t-distribution
am = arch_model(returns * 100, vol='GARCH', p=1, o=1, q=1, dist='t')
res = am.fit()
```

### 4.4 VaR/CVaR实现

```python
import numpy as np

def historical_var(returns, alpha=0.95):
    """历史模拟法VaR"""
    return -np.percentile(returns, (1 - alpha) * 100)

def historical_cvar(returns, alpha=0.95):
    """历史模拟法CVaR"""
    var = historical_var(returns, alpha)
    return -returns[returns <= -var].mean()

def parametric_var(returns, alpha=0.95):
    """参数法VaR"""
    from scipy.stats import norm
    mu, sigma = returns.mean(), returns.std()
    return -(mu + sigma * norm.ppf(1 - alpha))

def cornish_fisher_var(returns, alpha=0.95):
    """Cornish-Fisher修正VaR"""
    from scipy.stats import norm
    mu, sigma = returns.mean(), returns.std()
    S, K = returns.skew(), returns.kurtosis()
    z = norm.ppf(1 - alpha)
    z_cf = z + (z**2 - 1)*S/6 + (z**3 - 3*z)*K/24 - (2*z**3 - 5*z)*S**2/36
    return -(mu + sigma * z_cf)
```

---

## 五、参考文献与来源

### 学术论文
- Markowitz, H. (1952). "Portfolio Selection." *Journal of Finance*.
- Black, F. & Litterman, R. (1992). "Global Portfolio Optimization." *Financial Analysts Journal*.
- Lopez de Prado, M. (2016). "Building Diversified Portfolios that Outperform Out-of-Sample." *Journal of Portfolio Management*.
- Michaud, R. (1989). "The Markowitz Optimization Enigma: Is 'Optimized' Optimal?" *Financial Analysts Journal*.
- Kelly, J.L. (1956). "A New Interpretation of Information Rate." *Bell System Technical Journal*.

### 2025前沿
- ACM ICAIF 2025: "Regret-Driven Portfolios: LLM-Guided Smart Clustering for Optimal Allocation"
- ICLR 2025 Workshop: "Integrating LLM-Generated Views into Mean-Variance Optimization Using the Black-Litterman Model"
- SSGA / JPM 2025: "Strategic Asset Allocation with Alternative Investments: An Integrated Approach"
- arXiv 2025: "skfolio: Portfolio Optimization in Python"
- Journal of Risk and Financial Management 2025: "Tsallis Entropy Revolutionises Portfolio Optimisation"
- arXiv 2024: "Portfolio Stress Testing and VaR Incorporating Current Market Conditions"

### 行业报告
- SimCorp/Axioma 2025: 对冲基金四维风险分析框架
- Resonanz Capital 2025: "Risk Mitigation with Hedge Funds: An Allocator's Approach"
- OmegaPoint 2025: "Practitioner's Guide: Precision Hedges"
- CalPERS: Total Portfolio Approach模型
- LSEG ORE 13th Release (2025)

### Python库官方文档
- Riskfolio-Lib: https://riskfolio-lib.readthedocs.io/
- PyPortfolioOpt: https://pyportfolioopt.readthedocs.io/
- skfolio: https://skfolio.org/
- ORE: https://opensourcerisk.org/
- arch: https://arch.readthedocs.io/

---

*本知识图谱由风控建模团队基于2026年5月公开调研构建，将持续更新。*
