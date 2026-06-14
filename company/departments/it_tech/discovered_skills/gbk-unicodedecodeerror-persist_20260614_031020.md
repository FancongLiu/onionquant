---
name: gbk-unicodedecodeerror-persist
auto_generated: true
distilled_at: 2026-06-14T03:10:20.815283+08:00
source_task: GBK UnicodeDecodeError persists (122 occurrences in bg_scheduler_error.log) desp
---

# GBK UnicodeDecodeError persists (122 occurrences in bg_scheduler_error.log) desp

## 做了什么
Everything checks out. Here's the final summary:

## What was done

**Root cause**: `subprocess.run()`/`subprocess.Popen()` on Windows Python default to the system locale encoding (GBK). When subprocess output contains UTF-8 characters, decoding fails with `UnicodeDecodeError`.

**Fix**: Created `scripts/_subprocess_utils.py` — wrapper functions `run()` and `Popen()` that default to `encoding="utf-8", errors="replace"`.

**Changed 11 files** (added import + replaced `subprocess.run(` → `run(`, `

## 关键经验
- 自动蒸馏于 2026-06-14 03:10
- 来源: continuous_evolve.py v2 Hermes 学习循环

## 下次复用
如果遇到类似任务，加载此 skill 作为上下文。
