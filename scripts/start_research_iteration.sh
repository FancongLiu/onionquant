#!/bin/bash
# Start 24/7 LangGraph Research Iteration in WSL tmux
# Each cycle: one Claude Code invocation → commit → push → 10min cooldown

PROJECT="/mnt/e/2026_AgentStudy/Python_code"
SESSION="research-iter"

tmux kill-session -t "$SESSION" 2>/dev/null
sleep 1

# Write the iteration loop to a separate script to avoid escaping issues
cat > /tmp/research_loop.sh << 'LOOP_EOF'
#!/bin/bash
cd /mnt/e/2026_AgentStudy/Python_code
CYCLE=0
while true; do
  CYCLE=$((CYCLE+1))
  echo ""
  echo "=== CYCLE $CYCLE @ $(date) ==="
  echo ""
  claude -p "Read company/CHAIRMAN_PROMPT.md. Execute the NEXT undone LangGraph iteration task in priority order (P0 -> P1 -> P2 -> P3). Only do ONE task this cycle. After completing: verify it works, commit, push. Token budget: 50K max. If all P0-P3 tasks are done, output ALL_DONE and stop."
  if [ "$?" -eq 0 ] && echo "checking..." | grep -q "ALL_DONE"; then
    echo "All tasks complete!"
    break
  fi
  echo ""
  echo "=== Cycle $CYCLE complete ==="
  echo "Cooldown: 10 minutes..."
  sleep 600
done
echo "Iteration complete. Shell stays alive."
exec bash
LOOP_EOF

chmod +x /tmp/research_loop.sh

# Start in tmux
tmux new-session -d -s "$SESSION" \
  "echo '=== OnionQuant 24/7 Research Iteration ===';
   echo 'Pipeline: 11 departments -> FullResearchGraph';
   echo 'Token budget: 50K/cycle, same-session cache';
   echo 'Cooldown: 10 min between cycles';
   bash /tmp/research_loop.sh"

sleep 3
if tmux has-session -t "$SESSION" 2>/dev/null; then
    echo "OK: $SESSION running"
else
    echo "FAIL"
    exit 1
fi
