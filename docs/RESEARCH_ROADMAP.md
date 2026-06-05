# 🗺️ 技术路线总览

## 最终目标
**全球最强美股量化系统** — 能提前筛选出类似SMCI（超微电脑）、MU（美光）这样的超级成长股。

## 核心研究路线（10条路线并行）

### 路线1: 传统多因子模型
- **方法**：Fama-French五因子 + 动量 + 质量 + 低波动
- **优势**：学术界验证充分，解释性强
- **劣势**：Alpha衰减快，需要持续迭代
- **负责部门**：策略研究部

### 路线2: 机器学习价格预测
- **方法**：LSTM、Transformer、XGBoost、LightGBM
- **优势**：捕捉非线性关系，适应市场变化
- **劣势**：过拟合风险，需要大量特征工程
- **负责部门**：策略研究部

### 路线3: 深度强化学习交易
- **方法**：PPO、SAC、DQN for trading
- **优势**：端到端学习最优交易策略
- **劣势**：训练不稳定，奖励函数设计难
- **负责部门**：策略研究部

### 路线4: NLP舆情驱动策略
- **方法**：FinBERT、GPT情感分析 + 新闻/社交媒体
- **优势**：捕捉传统因子无法捕获的信号
- **劣势**：数据源稳定性，NLP中文适配
- **负责部门**：舆情情报部

### 路线5: 另类数据策略
- **方法**：卫星图像、信用卡数据、供应链数据、招聘数据
- **优势**：独特信息优势
- **劣势**：数据获取成本高，处理复杂
- **负责部门**：舆情情报部 + 数据工程部

### 路线6: 统计套利与配对交易
- **方法**：协整检验、卡尔曼滤波、均值回归
- **优势**：市场中性，稳定收益
- **劣势**：容量有限，需要高频数据
- **负责部门**：策略研究部

### 路线7: 高频交易微观结构
- **方法**：订单流分析、做市策略、延迟套利
- **优势**：高Sharpe，稳定盈利
- **劣势**：技术门槛极高，竞争激烈
- **负责部门**：策略研究部 + 交易执行部

### 路线8: 组合优化与风险管理
- **方法**：Black-Litterman、Risk Parity、Kelly Criterion
- **优势**：稳健收益，控制回撤
- **劣势**：依赖输入参数估计
- **负责部门**：风险管理部

### 路线9: 事件驱动策略
- **方法**：财报发布、分红公告、并购套利
- **优势**：独立于市场方向
- **劣势**：事件稀疏，容量有限
- **负责部门**：策略研究部 + 舆情情报部

### 路线10: 集成学习与元策略
- **方法**：Stacking、Blending多个子策略
- **优势**：降低过拟合，提高稳健性
- **劣势**：复杂度高，调参困难
- **负责部门**：策略研究部

## GitHub开源方案调研清单

### 综合性量化平台
- [ ] **vnpy** — 中国最流行的量化交易框架
- [ ] **zipline** — Python回测引擎（已停止维护但有大量fork）
- [ ] **backtrader** — 功能丰富的回测框架
- [ ] **QuantConnect/LEAN** — C#/Python跨平台引擎
- [ ] **Jesse** — 加密货币量化框架
- [ ] **Freqtrade** — 加密货币高频交易

### 机器学习量化
- [ ] **qlib** (Microsoft) — 最完善的AI量化平台
- [ ] **FinRL** — 深度强化学习金融交易
- [ ] **FinGPT** — LLM驱动的金融分析
- [ ] **TensorTrade** — 强化学习交易框架

### 数据源
- [ ] **yfinance** — Yahoo Finance数据
- [ ] **polygon.io** — 实时/历史美股数据
- [ ] **Alpaca** — 免佣金美股交易API
- [ ] **OpenBB Terminal** — 开源Bloomberg替代

### 因子研究
- [ ] **alphalens** — 因子分析工具
- [ ] **pyfolio** — 投资组合分析
- [ ] **empyrical** — 风险指标计算

## 论文追踪清单

### 顶级期刊/会议
- Journal of Finance
- Review of Financial Studies
- Journal of Financial Economics
- NeurIPS (金融/时序相关)
- ICML (金融/时序相关)
- KDD (金融/时序相关)

### 关键论文主题
- [ ] "Attention is All You Need" → 时序预测Transformer
- [ ] Deep Portfolio Theory
- [ ] Financial Sentiment Analysis with LLMs
- [ ] Reinforcement Learning for Portfolio Management
- [ ] Graph Neural Networks for Stock Prediction
- [ ] Alternative Data in Quantitative Finance

## 数据源路线

### 免费
- Yahoo Finance (yfinance)
- Alpha Vantage (限速)
- FRED (宏观经济)
- SEC EDGAR (财报XBRL)

### 付费（后续考虑）
- Polygon.io (实时美股)
- IEX Cloud
- Quandl/Nasdaq Data Link
- Bloomberg Terminal (终极方案)

### 另类数据
- 百度热搜API → 中文舆情
- 同花顺热度 → A股/中概股热度
- Reddit r/wallstreetbets → 散户情绪
- Twitter/X API → 社交情绪
- StockTwits → 投资者情绪

## 技术栈初步方案

| 层级 | 技术选择 | 备选 |
|------|---------|------|
| 数据层 | PostgreSQL + Parquet | MongoDB |
| 计算层 | NumPy + Pandas + Polars | Dask |
| ML框架 | PyTorch + XGBoost | TensorFlow |
| 回测引擎 | 自研事件驱动 | LEAN/vnpy |
| 前端 | Streamlit / Dash | Gradio |
| 编排 | Airflow / Prefect | Dagster |
| 语言 | Python主 + Rust加速 | Cython |

## 现阶段优先级

1. **P0**: 调研qlib、FinRL、FinGPT等开源方案 → 开源研究院
2. **P0**: 搭建数据Pipeline → 数据工程部
3. **P1**: 文献综述 → 学术研究部
4. **P1**: 舆情数据源接入 → 舆情情报部
5. **P2**: 回测引擎选型 → 回测引擎部
6. **P2**: 因子库搭建 → 策略研究部
