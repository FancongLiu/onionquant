"""情绪分析工具：FinBERT 加载/缓存，批量评分，聚合统计，中英文支持"""

import logging
import os
from functools import lru_cache

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

# 中文金融情感关键词词典（SnowNLP / FallBack 用）
_CN_BULLISH = {
    "涨", "涨停", "利好", "起飞", "梭哈", "满仓", "抄底", "看涨",
    "突破", "新高", "翻倍", "暴拉", "拉升", "牛市", "吃肉", "稳",
    "猛", "冲", "强势", "加仓", "持有", "拐点", "反转",
    "业绩超预期", "分红", "回购", "增持", "净流入", "主力",
}
_CN_BEARISH = {
    "跌", "跌停", "利空", "崩", "割肉", "空仓", "看跌", "爆仓",
    "破位", "新低", "腰斩", "砸盘", "熊市", "套牢", "跳水",
    "跑", "清仓", "减持", "净流出", "踩踏", "黑天鹅", "暴雷",
    "退市", "亏损", "业绩不及预期", "监管", "调查", "停牌",
}


def has_chinese(text: str) -> bool:
    """检测文本是否包含中文字符。"""
    return any("一" <= ch <= "鿿" for ch in text)


def score_chinese_text(text: str) -> dict[str, float]:
    """中文金融文本情绪评分 — SnowNLP 优先 + 金融关键词增强。

    与 score_text() 互补：score_text() 走 FinBERT (英文优先)，
    本函数专门处理中文金融文本，利用 SnowNLP + 金融领域关键词。
    """
    try:
        from snownlp import SnowNLP
        s = SnowNLP(text)
        base_p = max(0.0, min(1.0, s.sentiments))
    except ImportError:
        base_p = 0.5

    # 金融关键词增强：统计多空关键词出现次数，调整分数
    pos_hits = sum(1 for w in _CN_BULLISH if w in text)
    neg_hits = sum(1 for w in _CN_BEARISH if w in text)
    total_hits = pos_hits + neg_hits
    if total_hits > 0:
        keyword_p = pos_hits / total_hits
        # 加权融合：SnowNLP 权重 0.4 + 关键词 权重 0.6
        p = round(base_p * 0.4 + keyword_p * 0.6, 4)
    else:
        p = round(base_p, 4)

    return {"positive": p, "negative": round(1 - p, 4), "neutral": 0.0}


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


def score_text(text: str) -> dict[str, float]:
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


def _fallback(text: str) -> dict[str, float]:
    if has_chinese(text):
        return score_chinese_text(text)
    pos_w = {
        "bullish", "moon", "rocket", "profit", "gain", "green",
        "up", "moon", "squeeze",
    }
    neg_w = {
        "bearish", "dump", "loss", "red", "crash", "shorts",
        "drop", "short", "put",
    }
    words = set(text.lower().split())
    hits = {"positive": len(words & pos_w), "negative": len(words & neg_w)}
    total = hits["positive"] + hits["negative"] or 1
    return {k: round(v / total, 4) for k, v in hits.items()} | {"neutral": 0.0}


def batch_score(texts: list[str], batch_size: int = 32) -> list[dict[str, float]]:
    return [
        score_text(t)
        for i in range(0, len(texts), batch_size)
        for t in texts[i : i + batch_size]
    ]


def aggregate_sentiments(
    scores: list[dict[str, float]], weights: list[float] | None = None
) -> dict[str, float]:
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
