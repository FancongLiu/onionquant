#!/bin/bash
# CEO 24/7 loop — WSL tmux
# Inbox: batch every 30 min (read all, dedup, prioritize, merge to TASK_TRACKER)
# Research: 4x/trading day at session boundaries
# Token optimized: batch processing, cooldown enforced

PROJECT_DIR="/mnt/e/2026_AgentStudy/Python_code"
cd "$PROJECT_DIR" || exit 1
echo "[CEO Loop] Started $(date -Iseconds)"

LAST_RESEARCH=0
COOLDOWN=7200

while true; do
    NOW=$(date +%s)
    MINUTE=$(date +%M)
    HOUR=$(date +%H)

    # ─── Inbox batch: :07 and :37 ───
    if [ "$MINUTE" = "07" ] || [ "$MINUTE" = "37" ]; then
        PENDING=$(ls company/chairman_inbox/MSG_*.md 2>/dev/null | wc -l)
        if [ "$PENDING" -gt 0 ]; then
            echo "[$(date -Iseconds)] Inbox batch: $PENDING messages"
            claude -p --model deepseek-v4-pro --dangerously-skip-permissions \
"Batch inbox processing. $PENDING messages in company/chairman_inbox/MSG_*.md. Process AS A BATCH:
1. Read ALL messages at once.
2. Group duplicates — merge same-topic messages. If later contradicts earlier, keep LATEST.
3. Extract all action items → priority-ordered list (P0/P1/P2).
4. Update TASK_TRACKER.md: merge into existing table, resolve conflicts.
5. Execute quick items immediately, schedule long ones.
6. Move processed MSG_*.md to processed/.
7. Write summary to chairman_outbox/BRIEF_batch_\$(date +%Y%m%d_%H%M).md.
8. Run python scripts/wechat_sync_push.py to push to WeChat.
Batch efficiency: one session handles all. Be concise. No crons." \
              2>&1 | tail -5
        fi
    fi

    # ─── Research: 4x per trading day ───
    TRIGGER=""
    [ "$HOUR$MINUTE" = "2007" ] && TRIGGER="pre-market"
    [ "$HOUR$MINUTE" = "2137" ] && TRIGGER="market-open"
    [ "$HOUR$MINUTE" = "0407" ] && TRIGGER="post-market"
    [ "$HOUR$MINUTE" = "1007" ] && TRIGGER="overnight"

    if [ -n "$TRIGGER" ] && [ $((NOW - LAST_RESEARCH)) -gt $COOLDOWN ]; then
        echo "[$(date -Iseconds)] Research: $TRIGGER"
        claude -p --model deepseek-v4-pro --dangerously-skip-permissions \
"Trading session research ($TRIGGER). 3 parallel Agent forks:
(1) Positions+sector: MU/SNDK/NVDA/INTC/AMD/AVGO/SK Hynix + Samsung strike vote (May 22 start). Buy/sell/hold.
(2) Market hotspots: top movers, sector rotation, macro catalysts. What's hot.
(3) Watchlist: RKLB/ASTS/LUNR/RDW/COHR/LITE + SpaceX IPO/Starship.
After: write BRIEF to outbox, push WeChat, update context_state.json. Skip unfindable data. No crons." \
          2>&1 | tail -10
        LAST_RESEARCH=$NOW
    fi

    sleep 50
done