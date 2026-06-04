"""情绪分析工具：FinBERT 加载/缓存，批量评分，聚合统计，中英文支持"""

import os
import logging
from typing import List, Dict, Optional
from functools import lru_cache
import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


@lru_cache(maxsize=1)
def _get_finbert():
    try:
        from transformers import pipeline

        return pipeline(
            "sentiment-analysis",
            model=os.getenv("FINBERT_MODEL", "ProsusAI/finbert"),
            tokenizer=os.getenv("FINBERT_MODEL", "ProsusAI/finbert"),
            truncation=True,
            max_length=512,
        )
    except Exception as exc:
        logger.warning("FinBERT 加载失败 (%s)，使用回退", exc)
        return None


def score_text(text: str) -> Dict[str, float]:
    pipe = _get_finbert()
    if pipe is not None:
        try:
            results = pipe(text[:512])
            m = {"positive": 0.0, "negative": 0.0, "neutral": 0.0}
            for r in results:
                m[r["label"].lower()] = round(r["score"], 4)
            return m
        except Exception:
            pass
    return _fallback(text)


def _fallback(text: str) -> Dict[str, float]:
    has_zh = any("一" <= ch <= "鿿" for ch in text)
    if has_zh:
        try:
            from snownlp import SnowNLP

            p = SnowNLP(text).sentiments
            return {
                "positive": round(p, 4),
                "negative": round(1 - p, 4),
                "neutral": 0.0,
            }
        except ImportError:
            pass
    pos_w = {
        "bullish",
        "moon",
        "rocket",
        "profit",
        "gain",
        "green",
        "up",
        "moon",
        "squeeze",
    }
    neg_w = {
        "bearish",
        "dump",
        "loss",
        "red",
        "crash",
        "shorts",
        "drop",
        "short",
        "put",
    }
    words = set(text.lower().split())
    hits = {"positive": len(words & pos_w), "negative": len(words & neg_w)}
    total = hits["positive"] + hits["negative"] or 1
    return {k: round(v / total, 4) for k, v in hits.items()} | {"neutral": 0.0}


def batch_score(texts: List[str], batch_size: int = 32) -> List[Dict[str, float]]:
    return [
        score_text(t)
        for i in range(0, len(texts), batch_size)
        for t in texts[i : i + batch_size]
    ]


def aggregate_sentiments(
    scores: List[Dict[str, float]], weights: Optional[List[float]] = None
) -> Dict[str, float]:
    df = pd.DataFrame(scores)
    n = len(df)
    if n == 0:
        return {
            "positive_ratio": 0,
            "negative_ratio": 0,
            "neutral_ratio": 0,
            "weighted_score": 0.0,
            "count": 0,
        }
    w = np.array(weights if weights and len(weights) == n else [1 / n] * n)
    pos_r, neg_r, neu_r = (
        float((df["positive"] * w).sum()),
        float((df["negative"] * w).sum()),
        float((df["neutral"] * w).sum()),
    )
    return {
        "positive_ratio": round(pos_r, 4),
        "negative_ratio": round(neg_r, 4),
        "neutral_ratio": round(neu_r, 4),
        "weighted_score": round(pos_r - neg_r, 4),
        "count": n,
    }


def add_sentiment_columns(df: pd.DataFrame, text_column: str = "text") -> pd.DataFrame:
    return pd.concat(
        [
            df.reset_index(drop=True),
            pd.DataFrame(batch_score(df[text_column].tolist())),
        ],
        axis=1,
    )


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("texts", nargs="+")
    args = parser.parse_args()
    for t in args.texts:
        logger.info("TEXT: %s  ->  %s", t[:60], score_text(t))
