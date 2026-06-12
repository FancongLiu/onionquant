#!/bin/bash
# Claude Code Inbox Relay — 24/7 event-driven message processor
# Runs inside WSL tmux. Detects trigger file → invokes claude -p → writes reply.
#
# Architecture:
#   Server writes: company/.process_now (trigger) + chairman_inbox/MSG_*.md (message)
#   This script: detects trigger → calls claude -p with prompt from file
#   Claude Code: processes with full context (CLAUDE.md + memory + tools + WebSearch)
#   → writes reply to chairman_outbox/CLAUDE_REPLY_*.md
#   → clears trigger → moves message to processed/ → loops

PROJECT="/mnt/e/2026_AgentStudy/Python_code"
TRIGGER="$PROJECT/company/.process_now"
INBOX="$PROJECT/company/chairman_inbox"
OUTBOX="$PROJECT/company/chairman_outbox"
PROCESSED="$INBOX/processed"
PROMPT_FILE="/tmp/inbox_prompt.txt"

cd "$PROJECT"
mkdir -p "$OUTBOX" "$PROCESSED"

echo "[$(date '+%H:%M:%S')] Claude Inbox Relay started"
echo "  Trigger: $TRIGGER"
echo "  Engine:  claude -p (full context + tools)"
echo ""

while true; do
    if [ -f "$TRIGGER" ]; then
        # Read trigger data
        TRIGGER_DATA=$(cat "$TRIGGER" 2>/dev/null)
        rm -f "$TRIGGER"

        # Find the oldest pending message
        MSG_FILE=$(ls -t "$INBOX"/MSG_*.md 2>/dev/null | head -1)

        if [ -n "$MSG_FILE" ] && [ -f "$MSG_FILE" ]; then
            MSG_NAME=$(basename "$MSG_FILE")
            echo "[$(date '+%H:%M:%S')] Processing: $MSG_NAME"

            # Read message content
            MSG_CONTENT=$(cat "$MSG_FILE" 2>/dev/null)

            # Build prompt and write to file (avoid shell encoding issues)
            cat > "$PROMPT_FILE" << PROMPTEOF
你是 OnionQuant CEO Agent。董事长通过信箱发来消息。请基于项目上下文（CLAUDE.md、memory文件、任务队列、context_state）给出深度回复。

## 消息内容
$MSG_CONTENT

## 要求
1. 基于 CLAUDE.md 和 memory 文件中的项目上下文回答
2. 如果消息涉及股票/标的需要分析，使用 11 部门 LangGraph 管道
3. 如果需要最新信息，使用 WebSearch
4. 回复要精炼、结构化（Markdown）、可执行
5. 不要写"我会去搜索"然后停下来——直接执行搜索并把结果写进回复
6. 署名: -- CEO Agent
PROMPTEOF

            # Call Claude Code (same session = cache 99% hit)
            echo "[$(date '+%H:%M:%S')] Calling Claude Code..."
            REPLY=$(claude -p "$(cat $PROMPT_FILE)" --model deepseek-v4-pro --dangerously-skip-permissions 2>&1)
            CLAUDE_EXIT=$?

            # Write reply to outbox
            TS=$(date +%Y%m%d_%H%M%S)
            REPLY_FILE="$OUTBOX/CLAUDE_REPLY_$TS.md"
            cat > "$REPLY_FILE" << REPLYEOF
# CEO Agent 回复 (Claude Code 全上下文处理)

**时间**：$(TZ='Asia/Shanghai' date '+%Y-%m-%d %H:%M:%S') CST

$REPLY
REPLYEOF

            # Move message to processed
            mv "$MSG_FILE" "$PROCESSED/$MSG_NAME"

            REPLY_LEN=$(echo "$REPLY" | wc -c)
            echo "[$(date '+%H:%M:%S')] Done: $MSG_NAME → CLAUDE_REPLY_$TS.md ($REPLY_LEN chars)"
        fi
    fi
    sleep 2
done
