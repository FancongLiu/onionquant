"""Test P0-2: Error recovery — node failure never crashes the pipeline."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from unittest.mock import MagicMock, patch

from quant_framework.agents.full_research_graph import (
    DEPT_ORDER,
    FullResearchState,
    _call_llm,
    _make_dept_node,
)


def test_retry_on_transient_failure():
    """LLM call retries on transient error then succeeds."""
    mock_client = MagicMock()
    mock_client.chat.completions.create.side_effect = [
        TimeoutError("transient"),  # attempt 0 fails
        ConnectionError("transient"),  # attempt 1 fails
        MagicMock(choices=[MagicMock(message=MagicMock(content="OK after retry"))]),  # attempt 2 succeeds
    ]

    with patch("openai.OpenAI", return_value=mock_client):
        with patch("infrastructure.llm_provider.ENV_FILE", Path("__missing__.env")):
            with patch.dict("os.environ", {"DEEPSEEK_API_KEY": "test-key"}, clear=True):
                result = _call_llm("test", "system", max_retries=2)
                assert result == "OK after retry"
                assert mock_client.chat.completions.create.call_count == 3


def test_failure_after_all_retries_raises():
    """LLM call raises after exhausting all retries."""
    mock_client = MagicMock()
    mock_client.chat.completions.create.side_effect = TimeoutError("dead")

    with patch("openai.OpenAI", return_value=mock_client):
        with patch("infrastructure.llm_provider.ENV_FILE", Path("__missing__.env")):
            with patch.dict("os.environ", {"DEEPSEEK_API_KEY": "test-key"}, clear=True):
                try:
                    _call_llm("test", "system", max_retries=2)
                    assert False, "Should have raised"
                except TimeoutError:
                    assert mock_client.chat.completions.create.call_count == 3


def test_node_skip_on_failure():
    """Node returns SKIPPED instead of crashing pipeline."""
    node_fn = _make_dept_node("strategy_research")
    state: FullResearchState = {
        "user_request": "分析 NVDA",
        "tickers": ["NVDA"],
        "urgent": False,
        "steps_completed": ["data_engineering"],
        "errors": [],
        "skipped": [],
        "data_engineering_result": "数据就绪",
        "route": "data_engineering",
        "final_report": "",
    }
    for d in DEPT_ORDER:
        if f"{d}_result" not in state:
            state[f"{d}_result"] = ""

    with patch("quant_framework.agents.full_research_graph._call_llm", side_effect=RuntimeError("api down")):
        result = node_fn(state)
        assert "steps_completed" in result
        assert "strategy_research" in result["steps_completed"]
        assert "errors" in result
        assert any("strategy_research" in e for e in result["errors"])
        assert "[SKIPPED]" in result.get("strategy_research_result", "")


def test_downstream_node_gets_skip_context():
    """Downstream nodes are informed when upstream nodes were skipped."""
    node_fn = _make_dept_node("backtest_engine")
    state: FullResearchState = {
        "user_request": "分析 NVDA",
        "tickers": ["NVDA"],
        "urgent": False,
        "steps_completed": ["data_engineering", "strategy_research", "risk_management", "sentiment_intel"],
        "errors": ["sentiment_intel: RuntimeError('api down')"],
        "skipped": ["sentiment_intel"],
        "data_engineering_result": "数据就绪",
        "strategy_research_result": "看多评级",
        "risk_management_result": "中等风险",
        "sentiment_intel_result": "[SKIPPED] sentiment_intel: api down (retried 2x, pipeline continues)",
        "route": "backtest_engine",
        "final_report": "",
    }
    for d in DEPT_ORDER:
        if f"{d}_result" not in state:
            state[f"{d}_result"] = ""

    mock_result = "回测完成（在舆情缺失情况下）"
    with patch("quant_framework.agents.full_research_graph._call_llm", return_value=mock_result) as mock_llm:
        result = node_fn(state)
        # Verify the prompt included skip context
        call_prompt = mock_llm.call_args[0][0]
        assert "⚠" in call_prompt or "跳过" in call_prompt or "失败" in call_prompt
        assert "舆情情报部" in call_prompt
        assert result["backtest_engine_result"] == mock_result


if __name__ == "__main__":
    test_retry_on_transient_failure()
    print("PASS: test_retry_on_transient_failure")
    test_failure_after_all_retries_raises()
    print("PASS: test_failure_after_all_retries_raises")
    test_node_skip_on_failure()
    print("PASS: test_node_skip_on_failure")
    test_downstream_node_gets_skip_context()
    print("PASS: test_downstream_node_gets_skip_context")
    print("\nAll 4 error recovery tests PASSED")
