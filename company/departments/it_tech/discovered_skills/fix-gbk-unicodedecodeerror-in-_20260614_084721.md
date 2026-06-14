---
name: fix-gbk-unicodedecodeerror-in-
auto_generated: true
distilled_at: 2026-06-14T08:47:21.539227+08:00
source_task: Fix GBK UnicodeDecodeError in subprocess calls — recurs daily in bg_scheduler an
---

# Fix GBK UnicodeDecodeError in subprocess calls — recurs daily in bg_scheduler an

## 做了什么
## Summary

**Root cause**: On Windows/WSL, `subprocess.run(text=True)` defaults to GBK for pipe I/O. `PYTHONIOENCODING=utf-8` env var doesn't fix this — subprocess module uses `locale.getpreferredencoding()` for pipes, not `sys.stdout.encoding`.

**Why 2 prior fixes failed**:
- Commit `59096e5` created `_subprocess_utils.py` wrapper but missed raw `subprocess.run()` in `continuous_evolve.py`
- Commit `d6c8fe9` removed a broken import but left those raw calls untouched

**Changes made (5 files)*

## 关键经验
- 自动蒸馏于 2026-06-14 08:47
- 来源: continuous_evolve.py v2 Hermes 学习循环

## 下次复用
如果遇到类似任务，加载此 skill 作为上下文。
