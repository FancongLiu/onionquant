"""
通用短期催化交易决策模型 — 适用于任意标的的催化事件驱动仓位决策。

输入: 当前持仓 + 催化事件列表 + 风险参数
输出: 情景矩阵 + EV + 仓位建议 + 止损/止盈
"""

from dataclasses import dataclass, field
from typing import Optional
import math


@dataclass
class CatalystOutcome:
    """单个催化事件的可能结果"""
    label: str                    # 结果名称, 如 "发射成功" / "发射失败"
    probability: float            # 概率 0.0-1.0
    price_impact_pct: float       # 对股价的百分比影响, 如 +0.15 = +15%


@dataclass
class Catalyst:
    """单个催化事件"""
    name: str                     # 事件名, 如 "Starship V3 IFT-12"
    date: str                     # 日期
    outcomes: list[CatalystOutcome]
    time_to_event_hours: float = 0  # 距事件还有多少小时


@dataclass
class Scenario:
    """多个催化结果的组合 → 一个完整情景"""
    label: str
    catalyst_outcomes: dict[str, str]  # {事件名: 结果label}
    joint_probability: float           # 联合概率
    aggregate_impact_pct: float        # 累计价格影响 %
    price_target: float                # 情景目标价


@dataclass
class DecisionOutput:
    """模型输出"""
    scenarios: list[Scenario]
    expected_value: float              # 持仓 EV ($)
    expected_return_pct: float         # 预期收益率
    recommended_action: str            # "持有"/"加仓"/"减仓"/"清仓"
    position_pct: float                # 建议仓位占比 (0.0-1.0)
    stop_loss: float                   # 止损价
    take_profit: float                 # 止盈价
    risk_reward_ratio: float           # 风险收益比
    key_risk: str                      # 最大风险描述
    catalyst_timeline: list[str]       # 催化时间线摘要


def build_scenarios(catalysts: list[Catalyst], current_price: float) -> list[Scenario]:
    """笛卡尔积展开所有催化结果组合 → 情景矩阵"""
    if not catalysts:
        return []

    scenarios: list[Scenario] = []

    def recurse(idx: int, current_outcomes: dict[str, str],
                current_prob: float, current_impact: float):
        if idx == len(catalysts):
            label_parts = [f"{cat}:{out}" for cat, out in current_outcomes.items()]
            scenarios.append(Scenario(
                label=" | ".join(label_parts),
                catalyst_outcomes=dict(current_outcomes),
                joint_probability=current_prob,
                aggregate_impact_pct=current_impact,
                price_target=round(current_price * (1 + current_impact), 2),
            ))
            return

        cat = catalysts[idx]
        for outcome in cat.outcomes:
            current_outcomes[cat.name] = outcome.label
            recurse(
                idx + 1,
                current_outcomes,
                current_prob * outcome.probability,
                current_impact + outcome.price_impact_pct,
            )

    recurse(0, {}, 1.0, 0.0)

    # 按概率降序
    scenarios.sort(key=lambda s: s.joint_probability, reverse=True)
    return scenarios


def evaluate_position(
    ticker: str,
    current_price: float,
    cost_basis: float,
    shares: int,
    catalysts: list[Catalyst],
    max_position_pct: float = 1.0,
    max_loss_pct: float = -0.15,
    nav_premium_pct: Optional[float] = None,
) -> DecisionOutput:
    """
    核心入口：给定标的+催化 → 输出交易决策。

    Parameters
    ----------
    ticker: 标的代码
    current_price: 当前价格
    cost_basis: 持仓成本
    shares: 持仓股数
    catalysts: 催化事件列表 (按时间排序)
    max_position_pct: 最大仓位占比 (0-1)
    max_loss_pct: 最大可接受亏损 (负数)
    nav_premium_pct: NAV溢价率 (若有, 用于CEF类标的)

    Returns
    -------
    DecisionOutput: 完整决策
    """
    position_value = shares * current_price
    cost_value = shares * cost_basis

    # 1. 构建情景矩阵
    scenarios = build_scenarios(catalysts, current_price)

    # 2. 计算 EV
    ev_price = sum(s.price_target * s.joint_probability for s in scenarios)
    ev_return_pct = (ev_price / current_price - 1) * 100

    # 3. 识别极端情景
    best_scenario = max(scenarios, key=lambda s: s.price_target)
    worst_scenario = min(scenarios, key=lambda s: s.price_target)
    max_upside = (best_scenario.price_target / current_price - 1) * 100
    max_downside = (worst_scenario.price_target / current_price - 1) * 100

    # 4. Kelly 仓位计算 (基于 EV 和胜率)
    win_scenarios = [s for s in scenarios if s.aggregate_impact_pct > 0]
    win_prob = sum(s.joint_probability for s in win_scenarios)
    avg_win = (sum(s.aggregate_impact_pct * s.joint_probability for s in win_scenarios)
               / win_prob if win_prob > 0 else 0)
    loss_scenarios = [s for s in scenarios if s.aggregate_impact_pct <= 0]
    loss_prob = 1 - win_prob
    avg_loss = (sum(abs(s.aggregate_impact_pct) * s.joint_probability for s in loss_scenarios)
                / loss_prob if loss_prob > 0 else 0.01)

    # Kelly f* = (p_win * avg_win - p_loss * avg_loss) / (avg_win * avg_loss)
    # 对二元事件做 1/4 Kelly 收缩
    if avg_win > 0 and avg_loss > 0:
        kelly_raw = (win_prob * avg_win - loss_prob * avg_loss) / (avg_win * avg_loss)
        kelly = max(0, kelly_raw * 0.25)  # 1/4 Kelly
    else:
        kelly = 0

    # 5. 判断操作
    if ev_return_pct > 10 and kelly > 0.3:
        action = "加仓"
        position_pct = min(kelly, max_position_pct)
    elif ev_return_pct < -5 or max_downside < -20:
        action = "减仓"
        position_pct = min(kelly * 0.5, 0.5)
    elif nav_premium_pct and nav_premium_pct > 0.8:
        action = "减仓"  # NAV 溢价 >80% 系统性风险
        position_pct = 0.5
    elif kelly < 0.1:
        action = "持有观望"
        position_pct = min(kelly, 0.8)
    else:
        action = "持有"
        position_pct = min(kelly, max_position_pct)

    # 6. 止损/止盈
    # 止损: 最差情景目标价 (不取一半, 直接以最差情景为硬止损)
    stop_loss = round(worst_scenario.price_target, 2)
    # 止盈: 取上涨情景的加权平均目标价
    if win_scenarios:
        tp_price = sum(s.price_target * s.joint_probability for s in win_scenarios) / win_prob
    else:
        tp_price = ev_price
    take_profit = round(tp_price, 2)

    # 7. 风险收益比
    potential_risk = current_price - stop_loss
    potential_reward = take_profit - current_price
    rr_ratio = potential_reward / potential_risk if potential_risk > 0 else 999

    # 8. 催化时间线
    timeline = [f"{c.date}: {c.name}" for c in sorted(catalysts, key=lambda c: c.time_to_event_hours)]

    # 9. 最大风险
    max_risk_scenario = max(
        [s for s in scenarios if s.aggregate_impact_pct < 0],
        key=lambda s: abs(s.aggregate_impact_pct),
        default=worst_scenario,
    )
    key_risk = f"{max_risk_scenario.label} (P={max_risk_scenario.joint_probability:.0%}, {max_risk_scenario.aggregate_impact_pct:+.0%})"

    return DecisionOutput(
        scenarios=scenarios,
        expected_value=round(ev_price * shares - cost_value, 2),
        expected_return_pct=round(ev_return_pct, 1),
        recommended_action=action,
        position_pct=round(position_pct, 2),
        stop_loss=stop_loss,
        take_profit=take_profit,
        risk_reward_ratio=round(rr_ratio, 1),
        key_risk=key_risk,
        catalyst_timeline=timeline,
    )


def print_decision(output: DecisionOutput, ticker: str, current_price: float,
                   cost_basis: float, shares: int, catalysts: list[Catalyst]):
    """格式化打印决策输出"""
    position_value = shares * current_price
    pnl = shares * (current_price - cost_basis)

    print(f"\n{'='*60}")
    print(f"  {ticker} 短期催化决策模型")
    print(f"{'='*60}")
    print(f"  当前价: ${current_price:.2f}  成本: ${cost_basis:.2f}  "
          f"持仓: {shares}股 (${position_value:,.0f})  "
          f"浮盈: ${pnl:+,.0f}")
    print()

    # 催化时间线
    print("  [Timeline] 催化时间线:")
    for line in output.catalyst_timeline:
        print(f"    {line}")

    # 情景矩阵
    print(f"\n  [Matrix] 情景矩阵 ({len(output.scenarios)} 种组合):")
    print(f"  {'情景':<45} {'概率':>6} {'影响':>8} {'目标价':>8}")
    print(f"  {'-'*67}")
    for s in output.scenarios[:8]:  # 最多显示 8 行
        prob_str = f"{s.joint_probability:.0%}"
        impact_str = f"{s.aggregate_impact_pct:+.0%}"
        price_str = f"${s.price_target:.2f}"
        print(f"  {s.label:<45} {prob_str:>6} {impact_str:>8} {price_str:>8}")

    if len(output.scenarios) > 8:
        print(f"  ... 还有 {len(output.scenarios)-8} 个情景")

    # 决策
    ev_price_display = sum(s.price_target * s.joint_probability for s in output.scenarios)
    print(f"\n  [Decision] 决策: {output.recommended_action}")
    print(f"  {'-'*42}")
    print(f"  EV 价格:        ${ev_price_display:.2f}")
    print(f"  预期收益:        {(ev_price_display/current_price - 1)*100:+.1f}%")
    print(f"  建议仓位:        {output.position_pct:.0%}")
    print(f"  止损:           ${output.stop_loss:.2f}")
    print(f"  止盈(目标):     ${output.take_profit:.2f}")
    print(f"  风险收益比:      {output.risk_reward_ratio}:1")
    print(f"  最大风险:        {output.key_risk}")
    print()

    # 情景概率汇总
    print(f"  [Summary] 情景概率汇总:")
    win_prob = sum(s.joint_probability for s in output.scenarios if s.aggregate_impact_pct > 0)
    flat_prob = sum(s.joint_probability for s in output.scenarios if abs(s.aggregate_impact_pct) < 0.02)
    loss_prob = sum(s.joint_probability for s in output.scenarios if s.aggregate_impact_pct <= -0.02)
    print(f"    上涨: {win_prob:.0%}  横盘: {flat_prob:.0%}  下跌: {loss_prob:.0%}")


# ─── DXYZ 当前催化 ───

def dxyz_catalysts() -> list[Catalyst]:
    """DXYZ 当前催化事件 — 2026-05-18"""
    return [
        Catalyst(
            name="Starship V3 IFT-12",
            date="5/20 06:30 BJT",
            time_to_event_hours=35,
            outcomes=[
                CatalystOutcome("成功", 0.35, +0.15),
                CatalystOutcome("部分成功", 0.35, +0.03),
                CatalystOutcome("失败/爆炸", 0.20, -0.20),
                CatalystOutcome("推迟", 0.10, -0.05),
            ],
        ),
        Catalyst(
            name="SpaceX S-1 公开",
            date="5/20 全天",
            time_to_event_hours=48,
            outcomes=[
                CatalystOutcome("超预期(Starlink利润>$5B)", 0.30, +0.12),
                CatalystOutcome("符合预期($4-5B)", 0.45, +0.03),
                CatalystOutcome("低于预期/延迟", 0.25, -0.10),
            ],
        ),
        Catalyst(
            name="NVDA Q1 FY2027 财报",
            date="5/21 04:00 BJT",
            time_to_event_hours=57,
            outcomes=[
                CatalystOutcome("Beat+Raise (Q2>$90B)", 0.30, +0.05),
                CatalystOutcome("Beat (Q2~$87B)", 0.40, +0.01),
                CatalystOutcome("Miss/弱指引", 0.30, -0.08),
            ],
        ),
    ]


# ─── CLI ───

if __name__ == "__main__":
    # DXYZ 当前仓位
    ticker = "DXYZ"
    current_price = 53.0   # 盘前估算 ~$53
    cost_basis = 47.62
    shares = 588
    nav = 24.56            # NAV
    nav_premium = (current_price - nav) / nav  # ~116%

    catalysts = dxyz_catalysts()
    output = evaluate_position(
        ticker=ticker,
        current_price=current_price,
        cost_basis=cost_basis,
        shares=shares,
        catalysts=catalysts,
        max_position_pct=1.0,
        max_loss_pct=-0.20,
        nav_premium_pct=nav_premium,
    )

    print_decision(output, ticker, current_price, cost_basis, shares, catalysts)
    print(f"{'='*60}\n")
