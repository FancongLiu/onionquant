@echo off
chcp 65001 >nul
echo 🔧 启动线路 B：基础设施 + 前端迭代
echo ================================================
cd /d "e:\2026_AgentStudy\Python_code"
claude --worktree -p "读取 company/task_queues/task_queue_B.md。按任务清单 B1→B5 顺序执行，不要停。你是唯一处理 company/chairman_inbox/ 的线路，读到新消息后归档。铁律：不碰量化代码（线路A领域）。"
pause
