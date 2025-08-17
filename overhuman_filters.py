import pandas as pd
from decimal import Decimal
from utils import d
from overhuman_config import (MIN_VOL_PCT, DOJI_ATR_RATIO, VOL_BOOST_FACTOR,
                              BB_WIDTH_MIN, MIN_ADX, HTF_VOTE_THRESHOLD)

from overhuman_indicators import add_indicators

def market_filters_ok(df: pd.DataFrame, htf_map) -> bool:
    last = df.iloc[-1]
    atr = d(last.get('atr',0))
    vol_pct = d(last.get('vol_pct',0))
    vol_mean = d(last.get('vol_mean',0))
    rng = d(last.get('high',0)) - d(last.get('low',0))
    # Basic checks
    if atr == 0 or vol_pct == 0:
        return False
    if vol_pct < MIN_VOL_PCT:
        return False
    if rng < atr * d(DOJI_ATR_RATIO):
        return False
    if d(last.get('volume',0)) < vol_mean * d(VOL_BOOST_FACTOR):
        return False
    if d(last.get('bb_width',1.0)) < d(BB_WIDTH_MIN):
        return False
    # HTF votes
    htf_votes = 0
    total_htf = 0
    for interval, htf_df in htf_map.items():
        if htf_df is None or htf_df.empty:
            continue
        total_htf += 1
        hlast = htf_df.iloc[-1]
        if hlast['ema_fast'] > hlast['ema_slow']:
            htf_votes += 1
        elif hlast['ema_fast'] < hlast['ema_slow']:
            htf_votes -= 1
    if total_htf >= 2 and abs(htf_votes) < HTF_VOTE_THRESHOLD:
        return False
    # ADX
    if pd.isna(last.get('adx')):
        return False
    if d(last.get('adx',0)) < d(MIN_ADX):
        if d(last.get('volume',0)) < (vol_mean * d(VOL_BOOST_FACTOR)):
            return False
    return True

def pick_signal(df: pd.DataFrame) -> str:
    last = df.iloc[-1]
    bias_up = last['ema_fast'] > last['ema_slow']
    bias_down = last['ema_fast'] < last['ema_slow']
    close = d(last['close'])
    ema_slow = d(last['ema_slow'])
    margin = Decimal('0.0010')
    buy = bias_up and last['ema_slope']>0 and last['rsi']>51 and close > ema_slow * (Decimal('1')+margin)
    sell = bias_down and last['ema_slope']<0 and last['rsi']<49 and close < ema_slow * (Decimal('1')-margin)
    if buy: return 'BUY'
    if sell: return 'SELL'
    return 'HOLD'
