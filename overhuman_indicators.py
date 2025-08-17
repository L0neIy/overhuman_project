import pandas as pd
from overhuman_config import ATR_WINDOW, ADX_PERIOD, BB_WINDOW, VOL_WINDOW

def add_indicators(df: pd.DataFrame) -> pd.DataFrame:
    # RSI
    delta = df["close"].diff()
    gain = delta.clip(lower=0); loss = -delta.clip(upper=0)
    avg_gain = gain.rolling(14).mean()
    avg_loss = loss.rolling(14).mean().replace(0, 1e-9)
    rs = avg_gain/avg_loss
    df["rsi"] = 100 - (100/(1+rs))
    # EMA
    df["ema_fast"] = df["close"].ewm(span=5, adjust=False).mean()
    df["ema_slow"] = df["close"].ewm(span=13, adjust=False).mean()
    df["ema_slope"] = df["ema_fast"] - df["ema_fast"].shift(2)
    # ATR
    hl = df["high"] - df["low"]
    hc = (df["high"] - df["close"].shift()).abs()
    lc = (df["low"] - df["close"].shift()).abs()
    tr = pd.concat([hl,hc,lc], axis=1).max(axis=1)
    df["atr"] = tr.rolling(ATR_WINDOW).mean()
    # Volatility + volume
    df["ret"] = df["close"].pct_change()
    df["vol_pct"] = df["ret"].rolling(VOL_WINDOW).std() * 100
    df["vol_mean"] = df["volume"].rolling(30).mean()
    # Bollinger
    df["bb_mid"] = df["close"].rolling(BB_WINDOW).mean()
    df["bb_std"] = df["close"].rolling(BB_WINDOW).std()
    df["bb_upper"] = df["bb_mid"] + 2*df["bb_std"]
    df["bb_lower"] = df["bb_mid"] - 2*df["bb_std"]
    df["bb_width"] = (df["bb_upper"] - df["bb_lower"]) / df["bb_mid"].replace(0, 1e-9)
    # ADX
    period = ADX_PERIOD or 14
    up_move = df['high'].diff()
    down_move = -df['low'].diff()
    plus_dm = ((up_move > down_move) & (up_move > 0)) * up_move
    minus_dm = ((down_move > up_move) & (down_move > 0)) * down_move
    tr2 = pd.concat([(df['high'] - df['low']).abs(),
                     (df['high'] - df['close'].shift()).abs(),
                     (df['low'] - df['close'].shift()).abs()], axis=1).max(axis=1)
    atr_adx = tr2.rolling(period).mean().replace(0, 1e-9)
    plus_di = 100 * (plus_dm.rolling(period).sum() / atr_adx)
    minus_di = 100 * (minus_dm.rolling(period).sum() / atr_adx)
    dx = 100 * (plus_di - minus_di).abs() / (plus_di + minus_di).replace(0, 1e-9)
    df['adx'] = dx.rolling(period).mean()
    return df
