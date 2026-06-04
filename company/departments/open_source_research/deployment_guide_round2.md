# Qlib 与 FinRL 本地部署研究报告 (Round 2)

> 研究日期: 2026-05-17
> 目标平台: Windows 11
> 当前环境: Python 3.12.10, .venv at `E:/2026_AgentStudy/Python_code/.venv`

---

## 目录

1. [Qlib 部署方案](#1-qlib-部署方案)
2. [FinRL 部署方案](#2-finrl-部署方案)
3. [美股数据适配方案](#3-美股数据适配方案)
4. [Alpha 因子挖掘示例](#4-alpha-因子挖掘示例)
5. [FinRL-X 最新进展](#5-finrl-x-最新进展)
6. [环境兼容性检查](#6-环境兼容性检查)
7. [替代方案研究](#7-替代方案研究)
8. [最终推荐](#8-最终推荐)

---

## 1. Qlib 部署方案

### 1.1 框架简介

Qlib 是微软亚洲研究院开源的 AI 量化投资框架，提供数据采集、因子工程、模型训练、回测评估等全流程支持。当前稳定版本 **0.9.7**。

### 1.2 安装步骤

#### 前提条件

- **Visual Studio Build Tools 2022**（必须，否则 SCS/Cython 扩展编译失败）
  - 下载地址: https://visualstudio.microsoft.com/downloads/#build-tools-for-visual-studio-2022
  - 安装时勾选 "使用 C++ 的桌面开发"（Desktop development with C++）
  - 确保包含 MSVC 编译器工具链和 Windows SDK

#### 推荐安装命令

```bash
# 方式一: pip 直接安装（推荐）
pip install pyqlib

# 方式二: 源码安装
git clone https://github.com/microsoft/qlib.git
cd qlib
pip install -e .
```

#### Windows 专用避坑步骤

由于当前 .venv 基于 Python 3.12.10，而 Qlib 依赖的 SCS（Splitting Conic Solver）包在 Windows 上编译可能失败，建议按以下顺序操作：

```bash
# 1. 升级构建工具
python -m pip install --upgrade pip setuptools wheel

# 2. 预编译 SCS（关键步骤，避免 Cython 编译报错）
#    如果使用 conda:
conda install -c conda-forge scs
#    若使用 pip 纯环境:
pip install numpy cython pyarrow   # 先安装基础依赖

# 3. 安装 Qlib
pip install pyqlib

# 4. 验证安装
python -c "import qlib; qlib.init(); print(qlib.__version__)"
```

如果安装仍报错 `metadata-generation-failed`，有两种选择：
- **方案 A**: 降级 Python 到 3.10，已知兼容性最好
- **方案 B**: 使用 Docker 容器运行 Qlib

### 1.3 验证安装

```python
import qlib
from qlib.config import REG_CN

# 初始化（需要先下载数据）
provider_uri = "~/.qlib/qlib_data/cn_data"  # 改为实际路径
qlib.init(provider_uri=provider_uri, region=REG_CN)
print(f"Qlib version: {qlib.__version__}")
```

### 1.4 Qlib 数据下载

```bash
# 下载中国 A 股数据（约 2GB）
python scripts/get_data.py qlib_data --target_dir ~/.qlib/qlib_data/cn_data --region cn
```

---

## 2. FinRL 部署方案

### 2.1 框架简介

FinRL 是 AI4Finance 基金会开源的金融强化学习框架，支持股票、加密货币、外汇等多品种交易策略。当前稳定版通过 `pip install finrl` 安装。

### 2.2 安装步骤

#### 前提条件

- **SWIG**（Simplified Wrapper and Interface Generator）— 构建 `box2d-py` 所需
- **Visual Studio Build Tools**（同上）
- **Python 3.10**（FinRL 对 Python 3.12 支持不完整）

#### 安装命令

```bash
# 1. 安装 SWIG（box2d-py 依赖）
pip install swig
pip install box2d-py

# 2. 安装 FinRL
pip install finrl

# 或从 GitHub 安装最新开发版
pip install git+https://github.com/AI4Finance-Foundation/FinRL.git

# 或源码安装
git clone https://github.com/AI4Finance-Foundation/FinRL.git
cd FinRL
pip install -r requirements.txt
pip install .
```

#### Windows 已知问题与解决方案

| 问题 | 症状 | 解决方案 |
|------|------|----------|
| `box2d-py` 构建失败 | `Could not build wheels for box2d-py` | 先装 SWIG: `pip install swig` |
| `ray` 版本不兼容 | `Could not find ray[default,tune]==1.3.0` | 使用 FinRL >= 0.3.6（已升级至 ray>=2） |
| `thriftpy2` 编译失败 | `python setup.py egg_info did not run successfully` | 使用 conda 环境或跳过 jqdatasdk |
| `swig.exe` 未找到 | `command 'swig.exe' failed` | 确保 SWIG 在 PATH 中 |
| 超时问题 | `Read timed out` | 切换国内镜像源或设置 `--default-timeout=100` |

#### 针对当前 .venv（Python 3.12.10）的特别说明

**FinRL 官方不推荐 Python 3.12。** 如果坚持在当前环境下安装，推荐使用 WSL2（Windows Subsystem for Linux）作为运行环境：

```bash
# 在 WSL2 Ubuntu 中
wsl --install -d Ubuntu

# 在 WSL 中安装
conda create -n finrl python=3.10
conda activate finrl
pip install finrl
```

### 2.3 验证安装

```python
from finrl.config import config
from finrl.meta.env_stock_trading.env_stocktrading import StockTradingEnv
print("FinRL imported successfully")
```

---

## 3. 美股数据适配方案

### 3.1 Qlib 适配美股

Qlib 原生支持美股数据采集，通过 Yahoo Finance Collector 实现。

#### 3.1.1 数据采集（三步流程）

**Step 1: 从 Yahoo Finance 下载原始数据**

```bash
python scripts/data_collector/yahoo/collector.py download_data \
    --source_dir ~/.qlib/stock_data/source/us_data \
    --region US \
    --start 2020-01-01 \
    --end 2025-12-31 \
    --delay 1 \
    --interval 1d
```

**Step 2: 数据归一化**

```bash
python scripts/data_collector/yahoo/collector.py normalize_data \
    --source_dir ~/.qlib/stock_data/source/us_data \
    --normalize_dir ~/.qlib/stock_data/normalize/us_data \
    --region US \
    --interval 1d
```

**Step 3: 转为 Qlib 二进制格式**

```bash
python scripts/dump_bin.py dump_all \
    --csv_path ~/.qlib/stock_data/normalize/us_data \
    --qlib_dir ~/.qlib/qlib_data/us_data \
    --freq day \
    --exclude_fields date,symbol
```

#### 3.1.2 初始化 Qlib（美股模式）

```python
from qlib.config import REG_US

qlib.init(provider_uri='~/.qlib/qlib_data/us_data', region=REG_US)
```

#### 3.1.3 支持的交易所和指数

| 项目 | 覆盖范围 |
|------|----------|
| 交易所 | NYSE, NASDAQ |
| 指数 | S&P 500 (`^GSPC`), NASDAQ-100 (`^NDX`), Dow Jones (`^DJI`) |
| 时区 | America/New_York |
| 频率 | 日线 (`1d`), 分钟线 (`1min`) |
| 符号格式 | 大写（如 `AAPL`） |

#### 3.1.4 中美市场差异对照

| 特性 | A 股 | 美股 |
|------|------|------|
| 交易单位 | 100 股（手） | 1 股 |
| 涨跌停限制 | 10% / 20% | 无限制 |
| Qlib Region | `REG_CN` | `REG_US` |
| 默认数据 | baostock / tushare | Yahoo Finance |

#### 3.1.5 已知限制与替代方案

- Yahoo Finance API 对分钟级数据仅保留最近 ~30 天
- Microsoft 官方的预打包美股数据（`--region us`）已过时（截至 2020-11）
- 社区方案: [Hugging Face metalwhale/stock_data](https://huggingface.co/datasets/metalwhale/stock_data) 提供预采集数据集
- 专业方案: 接入 **Polygon.io**, **IEX Cloud**, **Alpaca** 等付费数据源

### 3.2 FinRL 适配美股

FinRL 原生支持美股交易，主要使用 Yahoo Finance 和 FNSPID 数据集。

#### 3.2.1 Nasdaq-100 交易示例

FinRL Contest 2025 提供了标准美股交易流水线:

```python
# 下载 Nasdaq-100 数据
from finrl.meta.preprocessor.yahoodownloader import YahooDownloader

df = YahooDownloader(start_date='2010-01-01',
                     end_date='2025-12-31',
                     ticker_list=['AAPL', 'MSFT', 'GOOGL', 'AMZN', 'NVDA']).fetch_data()
```

#### 3.2.2 FNSPID 数据集

FinRL 2025 系列论文（FinRL-DeepSeek, DAPO-SR）使用 **FNSPID** 数据集:
- 涵盖 1999-2023 年
- 包含 1570 万条金融新闻记录
- 支持 Nasdaq-100 成分股回测

---

## 4. Alpha 因子挖掘示例

### 4.1 Qlib 内置因子

Qlib 提供 `Alpha 158` 和 `Alpha 360` 因子集:

```python
from qlib.contrib.data.handler import Alpha158

# 使用 Alpha158 因子集
handler = Alpha158(instruments='csi300',
                   start_time='2020-01-01',
                   end_time='2024-12-31',
                   freq='day')
```

### 4.2 AlphaAgent（2025 KDD 论文）

[AlphaAgent](https://github.com/RndmVariableQ/AlphaAgent) 是 2025 年 KDD 论文，LLM 驱动的自动化 Alpha 挖掘框架，深度集成 Qlib:

- **Idea Agent**: 提出市场假说指导因子构建
- **Factor Agent**: 从假说构造因子，具备正则化防过拟合
- **Eval Agent**: 回测验证并迭代优化

```bash
# 使用 AlphaAgent
pip install alphaagent

# 挖掘 Alpha 因子
alphaagent mine --potential_direction "<市场假说>"

# 多因子回测
alphaagent backtest --factor_path "./factors.csv"
```

### 4.3 FinRL 因子集成

FinRL-DeepSeek 使用 LLM（DeepSeek V3 / Qwen 2.5）生成情感信号作为额外特征:

```python
# 技术指标（MACD, RSI, etc.）
# + LLM 情感信号
# + 风险敏感奖励函数（CPPO）
```

---

## 5. FinRL-X 最新进展

### 5.1 概况

- **论文**: [FinRL-X: An AI-Native Modular Infrastructure for Quantitative Trading](https://arxiv.org/abs/2603.21330)
- **仓库**: [AI4Finance-Foundation/FinRL-Trading](https://github.com/AI4Finance-Foundation/FinRL-Trading)
- **状态**: 已接收至 PAKDD 2026 DMO-FinTech Workshop

### 5.2 相比 FinRL 的核心改进

| 能力 | FinRL（旧） | FinRL-X（新） |
|------|-------------|---------------|
| 范式 | 纯深度强化学习 | AI-Native（ML + DRL + LLM） |
| 架构 | 三层耦合单体 | 完全解耦模块化 |
| 策略 | 仅 DRL Agent | ML 选股 + DRL 择时 + 可扩展 |
| 回测 | 自定义循环 | 专业 `bt` 库引擎 |
| 实盘 | Alpaca 基础支持 | 多账户 + 风险控制 |
| 配置 | `config.py` | 类型安全的 Pydantic + `.env` |
| 数据源 | Yahoo Finance | Yahoo + FMP + WRDS（自动故障切换） |

### 5.3 安装方法

```bash
git clone https://github.com/AI4Finance-Foundation/FinRL-Trading.git
cd FinRL-Trading
pip install -r requirements.txt
```

### 5.4 历史回测表现（2018-01 至 2025-10）

论文报道 Rolling ML+DRL 和 Adaptive Rotation 策略跑赢 QQQ 和 SPY 基准。

---

## 6. 环境兼容性检查

### 6.1 当前环境快照

- **Python 版本**: 3.12.10
- **虚拟环境路径**: `E:/2026_AgentStudy/Python_code/.venv`
- **已安装关键包**: numpy 2.4.5, pandas 3.0.3, scipy 1.17.1, matplotlib 3.10.9, pyarrow 24.0.0, lxml 6.1.0
- **缺失关键依赖**: torch, tensorflow, stable-baselines3, swig, scs

### 6.2 兼容性矩阵

| 框架 | Python 3.12 支持 | Windows 支持 | GPU 支持 |
|------|------------------|-------------|----------|
| Qlib 0.9.7 | 官方支持（但 SCS 编译有坑） | 需 VS Build Tools | 通过 PyTorch |
| FinRL | **不支持**（推荐 3.10） | 依赖编译，推荐 WSL2 | 通过 PyTorch/SB3 |
| FinRL-X | 需验证 | 同 FinRL | 通过 PyTorch |
| PyTorch 2.9 | **完全支持** | 原生 Windows wheels | CUDA 12.6/12.4/12.1 |
| TensorFlow | **不支持**（需 3.11 以下） | 原生支持 | CUDA 12 |

### 6.3 PyTorch 安装命令（当前环境可用）

```bash
# CPU 版本（兼容性最好，立即可用）
pip install torch torchvision torchaudio

# CUDA 12.4 版本（如有 NVIDIA GPU）
pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu124
```

### 6.4 兼容性结论

**当前 .venv（Python 3.12.10）对 Qlib 勉强可行，对 FinRL 不推荐。** 关键风险点:

1. **FinRL** 在 Python 3.12 上未被官方验证，已知多个安装失败 issue
2. **SCS 编译** 在纯 pip 环境下可能需要 VS Build Tools 2022
3. **TensorFlow** 完全不支持 Python 3.12（但 FinRL 已迁移到 PyTorch，影响可控）
4. **numpy 2.x + pandas 3.x** 与 Qlib/FinRL 的兼容性需要实测验证（许多量化框架仍锁定 numpy<2）

---

## 7. 替代方案研究

### 7.1 横向对比总表

| 框架 | Stars | 定位 | 适用市场 | AI 能力 | 实盘 | 安装难度 | Python 版本 |
|------|-------|------|----------|---------|------|----------|-------------|
| **Qlib** | 高 | AI 量化研究 | A股/美股 | XGBoost/LGB/PyTorch/AutoML | 弱 | 中 | 3.8-3.12 |
| **FinRL** | ~14k | RL 量化交易 | 美股/A股/加密货币 | DRL(PPO/SAC/A2C/...) | 中 | 难(Win) | 3.10(推荐) |
| **FinRL-X** | 新 | AI-Native 全栈 | 美股 | ML+DRL+LLM | 强 | 中 | 待验证 |
| **VeighNa 4.0** | ~38k | 全栈量化平台 | A股/期货/多市场 | Lasso/LGB/MLP(新) | **最强** | 低(Studio) | 3.13 |
| **Freqtrade+FreqAI** | ~48k | AI 量化交易 | 加密货币为主 | LGB/XGB/FreqAI | 强 | 中 | 3.10-3.12 |
| **TradingAgents** | ~48k | 多 Agent LLM 交易 | 多市场 | LLM 多 Agent 协作 | 中 | 低 | 3.10+ |
| **RD-Agent** (微软) | ~12k | 策略自动生成 | 多市场 | LLM 代码生成 | 无 | 低 | 3.10+ |

### 7.2 各方案详细说明

#### 7.2.1 VeighNa 4.0 (vnpy) — 最适合 A 股实盘

2025 年 4 月发布的 v4.0 核心更新:
- **vnpy.alpha** 模块 — 受 Qlib 启发，集成 Alpha158 因子集
- 内置模型: Lasso, LightGBM, MLP
- 图形界面（VN Trader），开箱即用
- 30+ 交易接口（CTP、XTP、IB 等）
- Python 3.13 核心支持

**安装**:
```bash
pip install vnpy
# 或使用 VeighNa Studio 一键安装包
```

**适用场景**: A 股实盘交易、期货、期权

#### 7.2.2 Freqtrade + FreqAI — 最佳通用 AI 量化框架

GitHub 48k+ Stars，2025 年多家评测排名第一:
- FreqAI 集成 ML 流水线（LightGBM, XGBoost）
- Optuna 自动超参优化
- 回测 + 实盘一体化
- 社区活跃，文档完善

**局限**: 主要面向加密货币，股票需自行适配数据源

#### 7.2.3 TradingAgents — 多 Agent LLM 交易新范式

- 模拟真实交易公司架构（基本面分析师、情感分析师、技术分析师、牛熊研究员辩论、风控委员会）
- 支持 DeepSeek, Qwen, GPT, Claude, Gemini
- v0.2.4 支持结构化输出、LangGraph 持久化

#### 7.2.4 RD-Agent（微软研究院）— 自然语言生成策略

- 输入"创建一个动量+均值回归混合策略"即生成完整可回测代码
- 需要 LLM API 密钥（有成本）

### 7.3 Qlib 和 FinRL 是最优选择吗？

**结论: 不完全是。** 具体要看 OnionQuant 的战略定位:

| 定位 | 最优选择 |
|------|----------|
| **AI 研究驱动**（因子挖掘、模型训练） | **Qlib** 仍是首选，AI 能力最完整 |
| **深度强化学习交易** | **FinRL/FinRL-X** 是 RL 领域唯一成熟的框架 |
| **A 股实盘交易** | **VeighNa 4.0** 明显更好 |
| **美股实盘交易** | **FinRL-X** 或 **Freqtrade** + 美股数据适配 |
| **快速原型验证** | **RD-Agent** (LLM 生成策略) |
| **多 Agent LLM 协作** | **TradingAgents** |
| **OnionQuant 整体架构** | **Qlib(研究) + VeighNa(实盘)** 或 **Qlib + FinRL-X** |

**建议**: 不建议在 Qlib 和 FinRL 之间"二选一"，而是根据 OnionQuant "A 股为主还是美股为主"来决定技术栈:

- **纯 A 股路线**: VeighNa 4.0 (实盘) + Qlib (可选研究辅助)
- **美股/A 股混合路线**: Qlib (研究) + FinRL-X (RL 交易) + VeighNa (A 股实盘)
- **纯 AI 研究路线**: Qlib + AlphaAgent

---

## 8. 最终推荐

### 8.1 立即部署方案

鉴于当前 .venv 是 Python 3.12.10，按优先级排序:

**高优先级 — 可立即部署**:
```bash
# Qlib（需 VS Build Tools，可能需解决 SCS 编译问题）
pip install pyqlib

# PyTorch（当前环境完全兼容）
pip install torch torchvision torchaudio
```

**中优先级 — 需要新环境**:
```bash
# 创建 Python 3.10 环境给 FinRL
conda create -n quant python=3.10
conda activate quant
pip install swig box2d-py finrl
```

**低优先级 — 观察 FinRL-X 正式版发布后再部署**:
```bash
git clone https://github.com/AI4Finance-Foundation/FinRL-Trading.git
```

### 8.2 推荐行动路线

```
第 1 周: 安装 Qlib + PyTorch，跑通 A 股数据通道
          验证 Alpha158 因子集和简单模型训练

第 2 周: 建设美股数据通道（Yahoo Collector）
          验证 Qlib 在美股上的因子有效性

第 3 周: 创建 Python 3.10 环境部署 FinRL
          跑通 Nasdaq-100 交易示例

第 4 周: 评估 FinRL-X（如已发布正式版）
          同时评估 VeighNa 4.0 作为实盘执行层
```

### 8.3 风险提示

1. **Python 版本碎片化**: Qlib (3.12) vs FinRL (3.10) vs VeighNa (3.13) 需要维护多个环境
2. **Windows 编译**: 所有 C 扩展依赖的框架在 Windows 上均有编译坑，建议尽快标准化到 WSL2 或 Docker
3. **数据源稳定性**: Yahoo Finance API 不稳定，美股分钟级数据只有 30 天回溯，正式研究需付费数据源
4. **numpy/pandas 版本锁定**: 量化框架通常对 numpy/pandas 版本敏感，升级需谨慎测试

---

## 附录: 参考资料

- Qlib 官方文档: https://qlib.readthedocs.io/
- Qlib GitHub: https://github.com/microsoft/qlib
- FinRL 官方文档: https://finrl.readthedocs.io/
- FinRL GitHub: https://github.com/AI4Finance-Foundation/FinRL
- FinRL-X 论文: https://arxiv.org/abs/2603.21330
- FinRL-Trading: https://github.com/AI4Finance-Foundation/FinRL-Trading
- FinRL Contest 2025: https://github.com/Open-Finance-Lab/FinRL_Contest_2025
- AlphaAgent: https://github.com/RndmVariableQ/AlphaAgent
- VeighNa: https://github.com/vnpy/vnpy
- PyTorch 安装: https://pytorch.org/get-started/locally/
- 社区 Qlib Windows 安装经验: https://blog.csdn.net/qq_42725437/article/details/148499561
- Qlib SCS 问题解决: https://blog.gitcode.com/49744c35feb7946cd565b9b0878fa36e.html
