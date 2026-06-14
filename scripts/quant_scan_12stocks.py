#!/usr/bin/env python3
"""Quantitative scan for 12 target stocks — DXYZ priority."""

import numpy as np
import pandas as pd
import yfinance as yf

TICKERS = ["DXYZ", "INTC", "MU", "AMD", "GE", "BABA", "JD", "NOK", "WDC"]
data = {}
for t in TICKERS:
    h = yf.Ticker(t).history("1y")["Close"]
    if len(h) > 100:
        data[t] = h
df = pd.DataFrame(data)
rets = df.pct_change().dropna()
corr = rets.corr()

print("=== Correlation Matrix ===")
header = f"{'':>7s} " + " ".join(f"{t:>7s}" for t in TICKERS)
print(header)
for t1 in TICKERS:
    row = f"{t1:>7s}: "
    for t2 in TICKERS:
        v = corr.loc[t1, t2] if t1 in corr.index and t2 in corr.columns else np.nan
        if t1 == t2:
            row += f"  {'--':>5s} "
        elif v > 0.5:
            row += f"  {v:5.2f}! "
        else:
            row += f"  {v:5.2f}  "
    print(row)

print("\n=== DXYZ Correlations ===")
for t in TICKERS:
    if t != "DXYZ" and t in corr.index:
        r = corr.loc["DXYZ", t]
        tag = "HIGH" if abs(r) > 0.5 else ("MED" if abs(r) > 0.3 else "LOW")
        print(f"DXYZ vs {t:6s}: r = {r:+.3f}  [{tag}]")

# DXYZ specific
print("\n=== DXYZ Metrics ===")
dxyz_r = rets["DXYZ"].dropna()
roll_sharpe = dxyz_r.rolling(30).mean() / dxyz_r.rolling(30).std() * (252**0.5)
print(f"Rolling 30d Sharpe: {roll_sharpe.iloc[-1]:.2f}")
print(f"30d ago Sharpe:     {roll_sharpe.iloc[-30]:.2f}")
print(f"Min Sharpe (1Y):    {roll_sharpe.min():.2f}")
print(f"Max Sharpe (1Y):    {roll_sharpe.max():.2f}")
print(f"Annual Vol:         {dxyz_r.std() * (252**0.5) * 100:.1f}%")
print(f"Skewness:           {dxyz_r.skew():+.2f}")
print(f"Kurtosis:           {dxyz_r.kurtosis():+.2f}")

# Best/worst performers
print("\n=== Top Picks by Sharpe ===")
stats = []
for t in TICKERS:
    r = rets[t].dropna()
    sharpe = (r.mean() / r.std()) * (252**0.5)
    cagr = (1 + r.mean()) ** 252 - 1
    maxdd = (df[t] / df[t].cummax() - 1).min()
    stats.append(
        {
            "Ticker": t,
            "Sharpe": sharpe,
            "CAGR": cagr,
            "MaxDD": maxdd,
            "Vol": r.std() * (252**0.5),
        }
    )
sdf = pd.DataFrame(stats).sort_values("Sharpe", ascending=False)
for _, row in sdf.iterrows():
    print(
        f"{row['Ticker']:6s}: Sharpe {row['Sharpe']:5.2f} | CAGR {row['CAGR'] * 100:6.1f}% | Vol {row['Vol'] * 100:5.1f}% | MaxDD {row['MaxDD'] * 100:6.1f}%"
    )

print("\nDone — quant_scan_12stocks")
