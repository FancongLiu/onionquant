@echo off
chcp 65001 >nul
echo 🧠 启动线路 C：研究分析 + 知识吸收
echo ================================================
cd /d "e:\2026_AgentStudy\Python_code"
claude --worktree -p "读取 company/task_queues/task_queue_C.md。按任务清单 C1→C5 顺序执行，不要停。只读模式：只产出分析报告，不编辑任何代码文件。所有产出写入 company/reports/。"
pause
