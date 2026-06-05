# 股票情绪/舆情数据知识图谱

> 所属部门: 舆情情报部
> 最后更新: 2026-05-17

---

## 一、知识领域全景

```
                        ┌─────────────────────────┐
                        │    股票情绪/舆情分析      │
                        │    (Sentiment Intel)     │
                        └─────────────────────────┘
                                   │
         ┌──────────┬──────────┬───┴───┬──────────┬──────────┐
         │          │          │       │          │          │
         ▼          ▼          ▼       ▼          ▼          ▼
      ┌──────┐  ┌──────┐  ┌──────┐ ┌──────┐  ┌──────┐  ┌──────┐
      │中文  │  │英文  │  │新闻  │ │另类  │  │情绪  │  │开源  │
      │舆情  │  │舆情  │  │数据  │ │数据  │  │算法  │  │工具  │
      └──────┘  └──────┘  └──────┘ └──────┘  └──────┘  └──────┘
```

---

## 二、节点定义与关系

### 2.1 节点类型说明

| 节点类型 | 符号 | 含义 | 示例 |
|---------|------|------|------|
| 数据源 | `[DS]` | 提供原始数据 | TradeStie, AKShare |
| 工具/库 | `[TL]` | 数据处理工具 | PRAW, SnowNLP |
| 模型/算法 | `[MA]` | 情绪分析模型 | FinBERT, VADER |
| 市场 | `[M]` | 适用市场 | 美股, A股, 港股 |
| 信号类型 | `[ST]` | 生成的信号类型 | 社交媒体情绪, 新闻情绪 |
| 概念 | `[C]` | 核心概念 | 情绪分数, 热度排名 |

---

## 三、核心实体关系图谱

### 3.1 数据源 → 市场 → 情绪类型 映射

```
[数据源]                    [市场]          [情绪类型]
─────────                   ─────           ─────────
TradeStie Reddit API ────── 美股  ────────── WSB社交媒体情绪
ApeWisdom ───────────────── 美股  ────────── Reddit热度情绪
StockTwits API ──────────── 美股  ────────── 金融社交情绪
Alpha Vantage NEWS_SENTIMENT 美股  ───────── 新闻情感评分
Finnhub News ────────────── 美股  ────────── 新闻文本(需自建NLP)
Benzinga API ────────────── 美股  ────────── 专业金融新闻情绪
SEC EDGAR XBRL ──────────── 美股  ────────── 财报文本情绪
MarketAux ───────────────── 美股  ────────── 实体级新闻情绪
StockHark FinBERT ───────── 美股  ────────── Reddit深度学习情绪
Adanos ──────────────────── 美股  ────────── 社交媒体Buzz分数
NewsAPI.ai ──────────────── 全球  ────────── 通用新闻情绪

AKShare(百度热搜) ────────── A股/港股/美股 ── 中文热搜热度
AKShare(东方财富热榜) ────── A股  ────────── A股人气排名
AKShare(新闻情绪指数) ────── A股  ────────── 数库科技情绪指数
pysnowball(雪球) ────────── A股/美股 ─────── 中文股社区讨论
Tushare Pro(dc_hot) ─────── A股/港股/美股 ── 东方财富热度
Tushare Pro(ths_hot) ────── A股/美股 ────── 同花顺热度

SafeGraph ───────────────── 美股  ────────── 客流量(另类)
Orbital Insight ─────────── 全球  ────────── 卫星图像(另类)
LinkUp ──────────────────── 全球  ────────── 招聘先行指标(另类)
RavenPack ───────────────── 全球  ────────── 新闻情绪(华尔街标准)
Revelio Labs ────────────── 全球  ────────── 劳动力情绪(另类)
```

### 3.2 工具/库 → 使用场景 映射

```
[工具/库]            [使用场景]                        [配合数据源]
─────────            ──────────                       ───────────
AKShare ──────────── 获取中文金融数据(热搜/新闻/行情)   东方财富/百度/新浪
pysnowball ───────── 获取雪球社区讨论数据               雪球网
Tushare Pro ──────── 专业量化金融数据                  东方财富/同花顺
PRAW ─────────────── Reddit全平台数据爬取              Reddit
yfinance ─────────── 美股行情数据获取                   Yahoo Finance
FinBERT ──────────── 金融领域专用情绪分析              新闻/Reddit文本
SnowNLP ──────────── 中文文本情绪分析                  中文新闻/帖子
VADER ────────────── 英文通用情绪分析                  通用文本
HuggingFace TF ───── 预训练模型情绪分析                各类文本
OpenAI/Claude API ── LLM上下文感知情绪分析             各类文本
SEC-MCP ──────────── SEC EDGAR数据的MCP接口            SEC EDGAR
STREAMLIT ────────── 情绪仪表盘可视化                  多数据源聚合
```

### 3.3 情绪算法层级关系

```
Level 0: 计数/统计
    ├── ApeWisdom (提及计数)
    ├── AKShare 热度排名 (搜索量/点击量)
    └── Tushare 涨跌停统计 (涨停/跌停计数)

Level 1: 规则/词典
    ├── VADER (通用英文情绪词典)
    ├── SnowNLP (中文情感词典)
    ├── Loughran&McDonald (金融财务词典)
    └── TextBlob (简单极性评分)

Level 2: 传统ML
    ├── LogisticRegression + TF-IDF (简单分类)
    ├── SVM + 词向量 (中等精度)
    └── TradeStie (简单Bullish/Bearish分类)

Level 3: 深度神经网络
    ├── FinBERT (金融领域BERT, 开源)
    ├── cardiffnlp/twitter-roberta-base-sentiment (社交媒体)
    ├── Alpha Vantage NEWS_SENTIMENT (商业模型)
    └── StockHark FinBERT (时间衰减+去重增强)

Level 4: LLM/大模型
    ├── GPT-4.1 + News Text (OpenAI)
    ├── Claude 3.5+ OCR/Sonnet (Anthropic)
    ├── Gemini 2.0 Flash (Google)
    └── DeepSeek V3 (国产)
```

---

## 四、实体间关系矩阵

### 4.1 数据源间互补关系

```
TradeStie ──── 补充 ──── StockTwits   (社交媒体多平台交叉验证)
     │                        │
     │                        │
     ▼                        ▼
Alpha Vantage ─── 补充 ──── Finnhub     (新闻情绪多源验证)
     │                        │
     │                        │
     ▼                        ▼
AKShare ─────── 补充 ──── Tushare      (中文数据多源覆盖)
     │                        │
     │                        │
     ▼                        ▼
SEC EDGAR ───── 补充 ──── RavenPack    (基本面情绪+新闻情绪)
```

### 4.2 信号融合关系

```
                  ┌───────────────────┐
                  │  社交媒体情绪爆发    │ ← Reddit PRAW + TradeStie + StockTwits
                  │  (信号: 短期动量)    │
                  └────────┬──────────┘
                           │
                           ▼
                  ┌───────────────────┐
                  │  新闻情绪确认/背离   │ ← Alpha Vantage + Finnhub + Benzinga
                  │  (信号: 趋势加强/反转)│
                  └────────┬──────────┘
                           │
                           ▼
                  ┌───────────────────┐
                  │  基本面情绪验证     │ ← SEC EDGAR + 财报分析
                  │  (信号: 中长期方向)  │
                  └────────┬──────────┘
                           │
                           ▼
                  ┌───────────────────┐
                  │  另类数据先行指标    │ ← SafeGraph + LinkUp + Orbital
                  │  (信号: 业绩提前预判)│
                  └────────┬──────────┘
                           │
                           ▼
                  ┌───────────────────┐
                  │  综合情绪评分       │
                  │  (多源加权聚合)      │
                  └───────────────────┘
```

### 4.3 市场覆盖关系

```
              A股市场                 美股市场              港股市场
  ┌─────────────────────┐  ┌─────────────────────┐  ┌─────────────────┐
  │ AKShare(东方财富)    │  │ TradeStie(WSB)      │  │ AKShare(百度)   │
  │ AKShare(百度热搜)    │  │ StockTwits(社交)     │  │ Tushare(dc_hot) │
  │ AKShare(情绪指数)    │  │ Alpha Vantage(新闻)  │  │                 │
  │ Tushare(dc_hot)     │  │ Finnhub(综合)        │  │                 │
  │ Tushare(ths_hot)    │  │ Benzinga(专业新闻)    │  │                 │
  │ Tushare(涨停/资金流)  │  │ SEC EDGAR(财报)      │  │                 │
  │ pysnowball(雪球)     │  │ RavenPack(华尔街)     │  │                 │
  │ SnowNLP(中文情绪)     │  │ SafeGraph(客流量)    │  │                 │
  └─────────────────────┘  └─────────────────────┘  └─────────────────┘
```

---

## 五、核心概念定义

### 5.1 情绪/舆情关键指标

| 概念 | 定义 | 计算方式 | 数据源示例 |
|------|------|---------|-----------|
| **热度排名** | 股票在平台的搜索/讨论量排序 | 搜索频率/帖子数排名 | AKShare东方财富热榜, Tushare热榜 |
| **情绪分数** | 文本情绪的量化评分 | NLP模型输出(0~1或-1~+1) | Alpha Vantage, FinBERT |
| **看涨比例** | 正面情绪占总情绪的比例 | 正面帖数/(正面+负面) | TradeStie, StockTwits |
| **Buzz分数** | 社交媒体讨论热度 | 提及量+互动量综合 | Adanos(0-100) |
| **情绪背离** | 价格走势与情绪走势不一致 | 价格Δ vs 情绪Δ | 多源综合 |
| **恐慌贪婪指数** | 市场整体情绪状态 | 多指标综合(0-100) | 需自建 |
| **Mention Velocity** | 讨论量的变化速度 | (当期提及-上期提及)/上期 | Reddit分析 |
| **GIF情绪指数** | StockTwits GIF帖子的情绪信号 | GIF视觉分析 | StockTwits (学术研究) |
| **情绪指数** | 市场整体新闻情绪 | NLP处理每日数万篇新闻 | AKShare(数库科技) |

### 5.2 数据频率分类

| 频率 | 适用数据源 | 用途 |
|------|-----------|------|
| **实时/秒级** | WebSocket行情、StockTwits、Reddit PRAW | 高频交易信号 |
| **分钟级** | TradeStie(15min)、ApeWisdom(30min)、Adanos(1h) | 日内情绪监控 |
| **小时级** | Finnhub新闻、NewsAPI | 盘中决策 |
| **日级** | AKShare热榜、Tushare、Alpha Vantage | 每日情绪快照 |
| **周/月级** | SEC EDGAR、另类数据报告 | 中长期趋势判断 |

### 5.3 数据质量评估维度

```
数据质量 = f(权威性, 时效性, 覆盖度, 一致性, 可接入性)

权威性: SEC EDGAR > Benzinga > TradeStie > ApeWisdom
时效性: WebSocket > REST API(分钟) > 每日快照 > 报告
覆盖度: Finnhub > AKShare > NewsAPI > TradeStie
接入难度: 无需认证 < API Key < 积分制 < 付费企业合同
```

---

## 六、数据源竞争关系图谱

```
                   付费/企业级
                       │
         RavenPack ◄───┼───► Benzinga
          ($)          │         ($99+/月)
                       │
           Orbital ◄───┼───► SafeGraph
          ($$$$)       │         ($$$)
                       │
         Earnest  ◄────┼───► LinkUp
         ($$$$)        │         ($$)
                       │
          ─────────────┼─────────────
                       │
         Finnhub ◄─────┼───► Alpha Vantage
          (免费)        │         (免费)
                       │
         TradeStie ◄───┼───► ApeWisdom
          (免费)        │         (免费)
                       │
         AKShare ◄─────┼───► Tushare
          (免费)        │      (积分制)
                       │
          StockHark ◄──┼───► StockTwits
          (免费Beta)    │         (免费)
                       │
                   免费/开源
```

---

## 七、关键技术栈依赖关系

```
┌─────────────┐     ┌──────────────┐     ┌─────────────┐
│  数据采集层   │────▶│  情绪分析层   │────▶│  信号生成层   │
│             │     │              │     │             │
│ AKShare     │     │ FinBERT      │     │ 综合情绪分数  │
│ PRAW        │     │ VADER        │     │ 趋势信号     │
│ requests    │     │ SnowNLP      │     │ 背离检测     │
│ WebSocket   │     │ GPT-4/Claude │     │ 热度警报     │
│ yfinance    │     │ TextBlob     │     │             │
└──────┬──────┘     └──────┬───────┘     └──────┬──────┘
       │                   │                    │
       ▼                   ▼                    ▼
┌─────────────┐     ┌──────────────┐     ┌─────────────┐
│  Python     │     │ Transformers │     │ Pandas      │
│  asyncio    │     │ PyTorch      │     │ NumPy       │
│  httpx      │     │ scikit-learn │     │ SQL/NoSQL   │
│  cache      │     │ spaCy        │     │ Redis(缓存)  │
└─────────────┘     └──────────────┘     └─────────────┘
```

---

## 八、决策树: 选择合适的数据源

```
问题: 我需要什么类型的情绪数据?
         │
         ├── 美股社交媒体情绪?
         │    ├── Reddit → TradeStie(快速) / PRAW(自定义) / StockHark(深度)
         │    ├── StockTwits → StockTwits API
         │    └── 综合 → Adanos (Reddit+X合一)
         │
         ├── 美股新闻情绪?
         │    ├── 免费有限 → Alpha Vantage (25次/天)
         │    ├── 免费大量 → Finnhub + 自建NLP
         │    └── 付费专业 → Benzinga ($99+/月)
         │
         ├── 中概股/中文市场情绪?
         │    ├── A股热度 → AKShare (东方财富/百度热搜)
         │    ├── 中文社区 → pysnowball (雪球)
         │    └── 专业数据 → Tushare Pro (积分制)
         │
         ├── 基本面情绪?
         │    └── SEC EDGAR (免费, 财报文本)
         │
         └── 另类数据?
              ├── 客流 → SafeGraph
              ├── 就业 → LinkUp / Revelio Labs
              └── 卫星 → Orbital Insight / RS Metrics
```

---

## 九、已知限制与风险

| 风险类型 | 描述 | 影响程度 | 缓解措施 |
|---------|------|---------|---------|
| Reddit噪声 | 95%的Reddit内容为噪音(表情包、垃圾帖) | 高 | Bot过滤、时间衰减、置信度评分(StockHark方案) |
| Twitter API付费 | Twitter/X API付费化，成本大幅上升 | 高 | 用RSS+Reddit+StockTwits替代 |
| 中文数据反爬 | 雪球、东方财富有反爬机制 | 中 | 使用AKShare等已封装库，注意频率控制 |
| 免费额度限制 | Alpha Vantage仅25次/天 | 中 | 缓存策略+多API轮换+仅监控关键标的 |
| 另类数据成本 | 卫星/交易数据年费可达数万至数百万美元 | 高 | 初期聚焦免费指标(Revelio RPLS, SEC EDGAR) |
| 情绪信号延迟 | Reddit情绪领先股价30-60分钟 | 低 | 实时WebSocket接入+分钟级轮询 |
| 监管合规 | SEC关于MNPI(重大非公开信息)的指引 | 中 | 仅使用公开、聚合、匿名化的数据 |
| 市场覆盖盲区 | 美股小盘股覆盖不足 | 中 | 增加另类数据源进行交叉验证 |
