# overhuman_commander_ultra_fixed.py
import time, os, collections
import pandas as pd
from decimal import Decimal, ROUND_DOWN, ROUND_UP, getcontext
from typing import Dict, Deque, Tuple, List
from utils import setup_client, load_env_overrides, retry, d, adjust_qty_step
import overhuman_config as cfg
from overhuman_indicators import add_indicators
from overhuman_filters import market_filters_ok, pick_signal
from overhuman_risk import compute_risk_based_qty
from overhuman_execution import (
    get_position_side_amt, can_open_new_side, place_entry_market,
    place_brackets, maybe_micro_tp, maybe_rearm_adaptive, _handle_trade_exit, calc_atr_sl_tp
)
from overhuman_telemetry import append_telemetry, metrics

getcontext().prec = 18

# ===== Feature flags / defaults =====
AFTERBURNER_ENABLED       = getattr(cfg, 'AFTERBURNER_ENABLED', True)
AFTERBURNER_SCAN_FACTOR   = getattr(cfg, 'AFTERBURNER_SCAN_FACTOR', 3)
AFTERBURNER_MAX_DURATION  = getattr(cfg, 'AFTERBURNER_MAX_DURATION_SEC', 300)

ACEZ_ENABLED              = getattr(cfg, 'ACEZ_ENABLED', True)
ACEZ_WINDOW_SEC           = getattr(cfg, 'ACEZ_WINDOW_SEC', 45)
ACEZ_DROP_PCT             = getattr(cfg, 'ACEZ_DROP_PCT', 1.0)
ACEZ_SPIKE_PCT            = getattr(cfg, 'ACEZ_SPIKE_PCT', 1.0)
ACEZ_COOLDOWN_SEC         = getattr(cfg, 'ACEZ_COOLDOWN_SEC', 120)
ACEZ_QTY_FACTOR           = getattr(cfg, 'ACEZ_QTY_FACTOR', Decimal('0.5'))
ACEZ_TP_SL_ATR_MULT       = getattr(cfg, 'ACEZ_TP_SL_ATR_MULT', (Decimal('0.6'), Decimal('0.8')))

SYMBOLS: List[str]        = getattr(cfg, 'SYMBOLS', [getattr(cfg, 'SYMBOL', 'BTCUSDT')])
MAX_OPEN_POS              = getattr(cfg, 'MAX_OPEN_POSITIONS', 2)

# ===== Helpers =====
def ensure_futures_settings(client, symbol, leverage, hedge_mode):
    def _lev(): return client.futures_change_leverage(symbol=symbol, leverage=leverage)
    def _pmode(): return client.futures_change_position_mode(dualSidePosition=hedge_mode)
    try: retry(_lev, on_error=lambda e,i: print('[WARN]', symbol, 'leverage attempt', i, e))
    except Exception as e: print('[WARN]', symbol, 'leverage:', e)
    try: retry(_pmode, on_error=lambda e,i: print('[WARN]', symbol, 'position mode attempt', i, e))
    except Exception as e: print('[WARN]', symbol, 'position mode:', e)

def fetch_filters(client, symbol):
    info = client.futures_exchange_info()
    sym = next((s for s in info['symbols'] if s['symbol']==symbol), None)
    if not sym: raise RuntimeError(f'Symbol not found: {symbol}')
    tick=d('0.1'); step=d('0.001'); min_notional=d('5'); min_qty=d('0.001')
    for f in sym.get('filters', []):
        t=f.get('filterType')
        if t=='PRICE_FILTER': tick=d(f.get('tickSize', tick))
        elif t=='LOT_SIZE': step=d(f.get('stepSize', step)); min_qty=d(f.get('minQty', min_qty))
        elif t in ('MIN_NOTIONAL',): v=f.get('notional') or f.get('minNotional'); min_notional=d(v) if v else min_notional
    return {'tick': tick, 'step': step, 'min_notional': min_notional, 'min_qty': min_qty}

def adjust_qty_for_exchange(qty: Decimal, step: Decimal, min_notional: Decimal, mark: Decimal) -> Decimal:
    """ปรับ qty ให้ปัด step size และผ่าน min_notional"""
    qty = qty.quantize(step, rounding=ROUND_DOWN)
    if qty * mark < min_notional:
        qty = (min_notional / mark).quantize(step, rounding=ROUND_UP)
    return qty

def get_klines(client, symbol, interval=cfg.INTERVAL, limit=300):
    kl = client.futures_klines(symbol=symbol, interval=interval, limit=limit)
    df = pd.DataFrame(kl, columns=['open_time','open','high','low','close','volume','close_time','quote_volume','trades','taker_buy_base','taker_buy_quote','ignore'])
    for c in ['open','high','low','close','volume']: df[c] = df[c].astype(float)
    return df

def _percent_change(a: float, b: float) -> float:
    if b==0: return 0.0
    return (a-b)*100.0/b

def detect_collapse_spike(price_window: Deque[Tuple[float,float]], now_ts: float, window_sec: int, drop_pct: float, spike_pct: float):
    while price_window and (now_ts-price_window[0][0]>window_sec): price_window.popleft()
    if len(price_window)<2: return None
    prices = [p for _,p in price_window]; cur=prices[-1]; mx=max(prices); mn=min(prices)
    drop=_percent_change(mx,cur); spike=_percent_change(cur,mn)
    if drop>=drop_pct: return ('COLLAPSE',drop)
    if spike>=spike_pct: return ('SPIKE',spike)
    return None

# ===== Main Loop =====
def main():
    load_env_overrides(cfg)
    client = setup_client(cfg.TESTNET)
    print('[BOOT] Connected to Binance Futures Testnet' if cfg.TESTNET else '[BOOT] Connected to Binance Futures')

    try: bal=client.futures_account_balance(); print('[OK] Auth sample:', bal[0])
    except Exception as e: print('[FATAL] Auth failed:', e); return

    # per-symbol settings
    filters_map: Dict[str, Dict] = {}
    price_window: Dict[str, Deque[Tuple[float,float]]] = {sym: collections.deque() for sym in SYMBOLS}
    entry_ts_map: Dict[str, Dict[str,float]] = {sym:{'LONG':0.0,'SHORT':0.0} for sym in SYMBOLS}
    pyramid_count_map: Dict[str, Dict[str,int]] = {sym:{'LONG':0,'SHORT':0} for sym in SYMBOLS}
    acez_last_fire_ts: Dict[str, Dict[str,float]] = {sym:{'LONG':0.0,'SHORT':0.0} for sym in SYMBOLS}
    
    for sym in SYMBOLS:
        ensure_futures_settings(client, sym, cfg.LEVERAGE, cfg.HEDGE_MODE)
        filters_map[sym]=fetch_filters(client, sym)
        print(f"[INFO] {sym} Filters: tick={filters_map[sym]['tick']} step={filters_map[sym]['step']} minNotional={filters_map[sym]['min_notional']}")

    last_telemetry=time.time()

    def count_open_positions() -> int:
        total=0
        for s in SYMBOLS:
            for side in ('LONG','SHORT'):
                amt,_=get_position_side_amt(client,s,side)
                if amt!=0: total+=1
        return total

    while True:
        loop_start=time.time()
        try:
            for sym in SYMBOLS:
                df=get_klines(client, sym, cfg.INTERVAL)
                df=add_indicators(df)
                last_close=df.iloc[-1]['close'] if not df.empty else None
                print(f"[LOOP] {sym} at {time.strftime('%X')} last close={last_close}")

                if ACEZ_ENABLED and last_close is not None:
                    price_window[sym].append((loop_start,float(last_close)))
                    event=detect_collapse_spike(price_window[sym], loop_start, ACEZ_WINDOW_SEC, ACEZ_DROP_PCT, ACEZ_SPIKE_PCT)
                    if event:
                        etype, mag = event
                        side='LONG' if etype=='COLLAPSE' else 'SHORT'
                        if count_open_positions()<MAX_OPEN_POS and can_open_new_side(client,sym,side):
                            try:
                                last_row=df.iloc[-1]; mark=Decimal(str(last_row['close']))
                                filters=filters_map[sym]
                                base_qty=compute_risk_based_qty(client, filters, Decimal('0'), sym, Decimal('1')) * ACEZ_QTY_FACTOR
                                qty=adjust_qty_for_exchange(base_qty, filters['step'], filters['min_notional'], mark)
                                print(f"[ACE-Z] {sym} {etype} {mag:.2f}% -> {side} qty={qty}")
                                place_entry_market(client,sym,'BUY' if side=='LONG' else 'SELL',qty,cfg.HEDGE_MODE)
                                acez_last_fire_ts[sym][side]=loop_start
                            except Exception as e: print('[ACE-Z][WARN] place order failed:', sym, e)

                # ===== Signal / Filter =====
                if not market_filters_ok(df, {}):
                    print(f'[FILTER] {sym} HOLD (filter not passed)')
                else:
                    signal=pick_signal(df)
                    mark=Decimal(str(df.iloc[-1]['close']))
                    if signal!='HOLD':
                        side='LONG' if signal=='BUY' else 'SHORT'
                        if count_open_positions()<MAX_OPEN_POS and can_open_new_side(client,sym,side):
                            filters=filters_map[sym]
                            base_qty=compute_risk_based_qty(client, filters, Decimal('0'), sym, Decimal('1'))
                            qty=adjust_qty_for_exchange(base_qty, filters['step'], filters['min_notional'], mark)
                            print(f"[SIGNAL] {sym} {signal} | mark={mark} qty={qty}")
                            if qty*mark>=filters['min_notional']:
                                place_entry_market(client,sym,'BUY' if side=='LONG' else 'SELL',qty,cfg.HEDGE_MODE)

        except KeyboardInterrupt:
            print('\n[EXIT] KeyboardInterrupt received. Gracefully shutting down...')
            break
        except Exception as e:
            print('[ERROR]', e)

        # sleep dynamic
        sleep_sec=getattr(cfg,'LOOP_SECONDS',1)
        time.sleep(sleep_sec)

if __name__=='__main__':
    main()
