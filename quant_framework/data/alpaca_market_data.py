""""Alpaca Market Data Provider

提供美股实时行情数据，支持盘前/正常/盘后全时段。

Usage:
    from quant_framework.data.alpaca_market_data import AlpacaMarketData
    
    md = AlpacaMarketData()
    
    # 获取实时报价
    quotes = md.get_latest_quotes(['MU', 'NVDA', 'AVGO'])
    
    # 获取账户信息
    acc = md.get_account_info()
    
    # 批量获取价格
    prices = md.get_all_prices(['MU', 'NVDA', 'SPCF'])
"""

import os
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Literal
from dataclasses import dataclass

from dotenv import load_dotenv
from alpaca.data.historical.stock import StockHistoricalDataClient
from alpaca.data.requests import StockLatestQuoteRequest, StockLatestTradeRequest, StockBarsRequest
from alpaca.data.timeframe import TimeFrame
from alpaca.data.enums import DataFeed
from alpaca.trading.client import TradingClient

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
load_dotenv(os.path.join(PROJECT_ROOT, '.env'))

logger = logging.getLogger(__name__)


@dataclass
class MarketQuote:
    """实时报价数据"""
    symbol: str
    bid: float
    ask: float
    mid: float
    timestamp: datetime
    spread: float = 0.0
    
    def __post_init__(self):
        self.spread = self.ask - self.bid


@dataclass
class MarketBar:
    """K线数据"""
    symbol: str
    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float


class AlpacaMarketData:
    """Alpaca Markets 实时行情获取工具
    
    支持：
    - 最新报价 (quote): bid/ask/mid price
    - 最新成交 (trade): price/size
    - 分钟线数据 (bars): 1min/5min/1hour/1day
    - 盘前/正常/盘后全时段
    
    数据源：IEX (免费) 或 SIP (付费订阅)
    
    前提：已在 .env 中配置 ALPACA_API_KEY 和 ALPACA_SECRET_KEY
    """
    
    def __init__(self, feed: DataFeed = DataFeed.IEX):
        self.api_key = os.getenv('ALPACA_API_KEY', '')
        self.secret_key = os.getenv('ALPACA_SECRET_KEY', '')
        self.feed = feed
        self._data_client = None
        self._trading_client = None
        self._connected = False
        
        if self.api_key and self.secret_key:
            self._connect()
        else:
            logger.warning('No Alpaca credentials found in .env')
    
    def _connect(self):
        try:
            self._data_client = StockHistoricalDataClient(self.api_key, self.secret_key)
            self._trading_client = TradingClient(self.api_key, self.secret_key, paper=True)
            self._connected = True
            logger.info('AlpacaMarketData connected (IEX feed)')
        except Exception as e:
            logger.error(f'Connection failed: {e}')
            self._connected = False
    
    def is_connected(self) -> bool:
        return self._connected
    
    # === 实时报价 ===
    
    def get_latest_quotes(self, symbols: List[str]) -> Dict[str, MarketQuote]:
        """获取最新报价 (bid/ask)
        
        Args:
            symbols: 标的列表，如 ['MU', 'NVDA', 'AVGO']
        
        Returns:
            Dict[str, MarketQuote]: 每个标的的报价数据
        """
        if not self._connected:
            return {}
        
        try:
            req = StockLatestQuoteRequest(symbol_or_symbols=symbols)
            quotes = self._data_client.get_stock_latest_quote(req)
            result = {}
            for sym, q in quotes.items():
                result[sym] = MarketQuote(
                    symbol=sym,
                    bid=float(q.bid_price),
                    ask=float(q.ask_price),
                    mid=(float(q.bid_price) + float(q.ask_price)) / 2,
                    timestamp=q.timestamp
                )
            return result
        except Exception as e:
            logger.error(f'get_latest_quotes failed: {e}')
            return {}
    
    def get_latest_trades(self, symbols: List[str]) -> Dict[str, float]:
        """获取最新成交价格
        
        Args:
            symbols: 标的列表
        
        Returns:
            Dict[str, float]: 每个标的的最新成交价
        """
        if not self._connected:
            return {}
        
        try:
            req = StockLatestTradeRequest(symbol_or_symbols=symbols)
            trades = self._data_client.get_stock_latest_trade(req)
            return {sym: float(t.price) for sym, t in trades.items()}
        except Exception as e:
            logger.error(f'get_latest_trades failed: {e}')
            return {}
    
    # === 分钟线数据 ===
    
    def get_bars(
        self,
        symbols: List[str],
        timeframe: Literal['1min', '5min', '15min', '1hour', '1day'] = '1min',
        start: Optional[datetime] = None,
        end: Optional[datetime] = None,
        hours_back: int = 6
    ) -> Dict[str, List[MarketBar]]:
        """获取K线数据
        
        Args:
            symbols: 标的列表
            timeframe: 时间粒度 (1min/5min/15min/1hour/1day)
            start: 开始时间
            end: 结束时间
            hours_back: 默认回溯小时数
        
        Returns:
            Dict[str, List[MarketBar]]: 每个标的的K线数据
        """
        if not self._connected:
            return {}
        
        tf_map = {
            '1min': TimeFrame.Minute,
            '5min': TimeFrame.Hour,
            '15min': TimeFrame.Hour,
            '1hour': TimeFrame.Hour,
            '1day': TimeFrame.Day
        }
        
        if start is None:
            start = datetime.now() - timedelta(hours=hours_back)
        if end is None:
            end = datetime.now()
        
        try:
            req = StockBarsRequest(
                symbol_or_symbols=symbols,
                timeframe=tf_map.get(timeframe, TimeFrame.Minute),
                start=start,
                end=end,
                feed=self.feed
            )
            bars_data = self._data_client.get_stock_bars(req)
            
            result = {}
            for sym, bars in bars_data.data.items():
                result[sym] = [
                    MarketBar(
                        symbol=sym,
                        timestamp=bar.timestamp,
                        open=float(bar.open),
                        high=float(bar.high),
                        low=float(bar.low),
                        close=float(bar.close),
                        volume=float(bar.volume)
                    )
                    for bar in bars
                ]
            return result
        except Exception as e:
            logger.error(f'get_bars failed: {e}')
            return {}
    
    # === 账户信息 ===
    
    def get_account_info(self) -> Dict:
        """获取账户摘要
        
        Returns:
            Dict: 包含 buying_power, portfolio_value, cash, equity 等
        """
        if not self._connected:
            return {'connected': False}
        
        try:
            acc = self._trading_client.get_account()
            return {
                'connected': True,
                'status': str(acc.status),
                'buying_power': float(acc.buying_power),
                'portfolio_value': float(acc.portfolio_value),
                'cash': float(acc.cash),
                'equity': float(acc.equity),
                'daytrade_count': acc.daytrade_count
            }
        except Exception as e:
            return {'connected': False, 'error': str(e)}
    
    # === 批量获取 ===
    
    def get_all_prices(self, symbols: List[str]) -> Dict[str, Dict]:
        """批量获取所有标的的实时价格
        
        Args:
            symbols: 标的列表
        
        Returns:
            Dict[str, Dict]: 每个标的的完整价格信息 (bid/ask/mid/trade_price)
        """
        quotes = self.get_latest_quotes(symbols)
        
        result = {}
        for sym in symbols:
            q = quotes.get(sym)
            result[sym] = {
                'symbol': sym,
                'bid': q.bid if q else None,
                'ask': q.ask if q else None,
                'mid': q.mid if q else None,
                'spread': q.spread if q else None,
                'timestamp': str(q.timestamp) if q else None,
                'source': 'alpaca_iex'
            }
        return result
    
    def get_prices_dict(self, symbols: List[str]) -> Dict[str, float]:
        """快速获取实时中间价的简化接口
        
        Args:
            symbols: 标的列表
        
        Returns:
            Dict[str, float]: 每个标的的中间价
        """
        quotes = self.get_latest_quotes(symbols)
        return {sym: q.mid for sym, q in quotes.items()}


# === 全局单例 ===

_market_data_instance: Optional[AlpacaMarketData] = None

def get_market_data() -> AlpacaMarketData:
    """获取全局市场数据实例"""
    global _market_data_instance
    if _market_data_instance is None:
        _market_data_instance = AlpacaMarketData()
    return _market_data_instance


def get_realtime_prices(symbols: List[str]) -> Dict[str, float]:
    """快速获取实时价格的简化接口
    
    Usage:
        prices = get_realtime_prices(['MU', 'NVDA', 'AVGO'])
        print(prices['MU'])  # 1044.09
    """
    md = get_market_data()
    return md.get_prices_dict(symbols)


def get_account_summary() -> Dict:
    """快速获取账户信息"""
    md = get_market_data()
    return md.get_account_info()


if __name__ == '__main__':
    # 测试
    print('=== Alpaca Market Data Test ===')
    
    md = AlpacaMarketData()
    
    print()
    print('=== Account Info ===')
    acc = md.get_account_info()
    for k, v in acc.items():
        print(f'  {k}: {v}')
    
    print()
    print('=== Realtime Prices ===')
    symbols = ['MU', 'NVDA', 'AVGO', 'SPCF', 'SPCX', 'SNDK', 'COHR', 'LITE', 'RKLB', 'ASTS', 'LUNR', 'DXYZ']
    prices = md.get_all_prices(symbols)
    for sym, p in prices.items():
        print(f'  {sym}: mid={p['mid']:.2f} bid={p['bid']:.2f} ask={p['ask']:.2f}')

