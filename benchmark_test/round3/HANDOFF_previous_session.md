# HANDOFF — 上一会话归档（benchmark_test/round3 MU 财报前操作任务）

**归档时间**: 2026-06-22
**任务**: 回答董事长 MU 105 股 @ $1,106、2.8x 杠杆、6/24 财报前的操作问题
**状态**: 三份源文件已读全并核对一致；实时价未拉取（本会话被 API 错误打断）；4 个问题尚未作答。

---

## 一、已读源文件 & 核心数据（已核对一致）

### 1. briefing_and_prompt.md（权威 — 最新 6/18）
当前持仓：

| 标的 | 数量 | 成本 | 现价(6/18收) | 浮盈 |
|------|------|------|------|------|
| MU | 105 股 | ~$1,106 | $1,134（+8.7%） | +$2,940 |

| 账户 | |
|------|------|
| 净资产 | $42,074 |
| 总市值 | $119,068 |
| 杠杆 | ~2.8x |
| 融资比率 | ~99% |

### 2. chairman_position_tracker.json（last_updated 2026-06-19T02:00+08:00）
- current_position: MU 105 股, cost $1,106, mu_close_jun18 $1,134, unrealized_pnl $2,940, market_value $119,068
- account: equity $42,074, leverage ~2.8x, next_trading 北京时间 6/22 周一晚 9:30
- recent_trades 关键: 6/16 22:22 SELL MU 106 @ $1,074.04 (亏 $3,388) → 6/16 23:30 BUY SPCF 867 @ $41.75 → 清 SPCF → 6/17 BUY MU 105 @ $1,106
- market_context: mu_close_jun18 $1,134, sox_close_jun18 639, mu_earnings 6/24 周三, iran MOU 已签 6/19 正式签

### 3. memory/chairman_trading_records.md（⚠️ 6 天前旧状态，仅参考历史）
- 描述的是 6/16 WDC 139 股 + MU 4 股状态，**不是当前持仓**，已被 briefing/tracker 覆盖
- 唯一有用：6 月完整交易序列链条（见下）

## 二、6 月 5 次"卖赢家→追新标的"循环链条（来自 briefing + tracker）

1. 6/3: MU 逃顶 $1,061（+$36K）→ 追 MRVL $331 → $284 割肉（-$16K）
2. 6/12: SPCX 短线（+$1,644）
3. 6/15: 卖 MU $1,014（+$6,439）→ 追智谱港股（亏 HKD 11,450）
4. 6/16: 清智谱 → 买 WDC → 卖 WDC → 买 MU → 卖 MU（亏 $3,388）→ 买 SPCF → 卖 SPCF → 买 MU 105 @ $1,106
5. 特征: 现金停留不超过 1 小时；杠杆回到 2.8x；5 次重复

## 三、4 个待回答问题（原题见 briefing_and_prompt.md 第五节）

1. 6/22 复市后 MU 怎么操作？持有到 6/24 财报还是提前减仓？给具体股数和触发价。
2. 2.8x 杠杆全仓 MU @ $1,106，6/24 财报前。若财报后 beat 但跌 15%（如 AVGO），扛得住吗？算具体数字。
3. 若财报前 MU 从 $1,134 涨到 $1,200+，何时止盈？若跌回 $1,080 以下，止损吗？给精确条件。
4. 6 月 5 次"卖赢家→追新标的"循环，给 1-2 条具体可执行改进建议。

要求: 精确股数、精确触发价、计算可验证。

## 四、本会话踩过的坑（下个 AI 别重踩）

1. **GBK 编码**: 系统 Python 的 stdout 默认 GBK，打印 emoji（🔴等）会 UnicodeEncodeError。解决: 所有 python -c 前加 `PYTHONUTF8=1 PYTHONIOENCODING=utf-8`。或直接用 venv python: `E:/2026_AgentStudy/Python_code/.venv/Scripts/python.exe`（已确认装了 yfinance 1.3.0）
2. **系统 Python 无 yfinance**: 必须用 .venv 的 python。
3. **memory 过时**: `chairman_trading_records.md` 停在 6/16 WDC 状态，`chairman_position.md`（memory）停在 6/12 MU 104 股，`context_state.json` 的 chairman_position 字段停在 6/5 MRVL 471 股。**三者都不一致，以 briefing + tracker 为准**。
4. **Read 重复同文件返回 "Wasted call"**: 系统去重，但内容不进上下文。改用 `cat` via Bash。
5. **context_state.json 很大（33.8KB）**: 直接 Read 会被截断，用 python json.load + 提取字段。

## 五、Q2 margin call 计算框架（已构思，待验证）

- 净资产 $42,074，总市值 $119,068 → 融资负债 ≈ $119,068 - $42,074 - (105×$1,134) ≈ $119,068 - $42,074 - $119,070 ≈ 负值
  → 说明"总市值"可能含融资，需重新核算: 实际持仓 105×$1,134 = $119,070 ≈ 总市值。那么净资产 $42,074，融资 ≈ $119,070 - $42,074 = $76,996。
- margin call 触发: 通常维持保证金率 25%，即 (净值/市值) < 25% → 净值 < $119,070×0.25 = $29,768 时爆。
- MU 跌 15%: 股价 $1,134×0.85 = $963.9，市值 = 105×$963.9 = $101,210，净值 = $101,210 - $76,996 = $24,214 < $29,768 → **margin call**。
- ⚠️ 以上融资负债是推算，需从 tracker 或董事长确认实际融资额/保证金率再校准。

## 六、Q4 改进建议方向（待展开成可执行条目）

- 针对核心: 无法持有现金（最长 1 小时）+ 卖赢家立刻追新。
- 方向 A: 强制冷却期 — 卖出后现金停留 N 小时/天才能开新仓（机制化，靠规则不靠意志）。
- 方向 B: 分批止盈/止损单预挂 — 提前挂好 GTC 条件单，避免情绪化即时决策。
- 要给出"具体可执行"= 明确参数（冷却时长、挂单价位、股数）。

## 七、不要碰的东西

- ❌ 不改 `company/departments/execution/context_state.json`（cron 状态桥接）
- ❌ 不动 cron 配置 / background_scheduler
- ❌ 不写 outbox（除非需董事长决策）
- ✅ 只在 `benchmark_test/round3/` 下读写（项目自由区）

## 八、执行清单（下个 AI 接手后）

1. 读本文件（你已在此）
2. 用 venv python 拉 MU 实时价（周末可能只有 6/19 收盘）:
   `PYTHONUTF8=1 PYTHONIOENCODING=utf-8 E:/2026_AgentStudy/Python_code/.venv/Scripts/python.exe -c "import yfinance as yf; d=yf.Ticker('MU').history(period='1mo'); print(d['Close'].tail(10)); print('SOXX'); print(yf.Ticker('SOXX').history(period='1mo')['Close'].tail(5))"`
3. WebSearch 检索: AVGO 最近一次财报 beat 后跌幅（验证 Q2 "beat 但跌 15%" 假设）、MU 6/24 财报期权隐含波动/预期
4. 基于实时价校准 Q1/Q3 触发价，完成 4 个问题作答
5. 产出写到 `benchmark_test/round3/analysis_round3.md`
