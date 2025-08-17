import time, csv, os
from decimal import Decimal
from typing import Dict, Tuple
import pandas as pd
from binance.enums import *
from utils import d, round_step, retry
from overhuman_config import (BASE_SL_PCT, BASE_TP_PCT, ADAPT_TRIGGER_ATR, TP_EXPAND_FACTOR,
                              TRAIL_SL_LOCK_PCT, REARM_COOLDOWN_SEC, MAX_PYRAMID_LEVELS,
                              ALLOW_PYRAMID, MICRO_TP_TRIGGER_MINUTES, MICRO_TP_PCT,
                              TRADE_LOG_FILE, LOSS_STREAK_LIMIT, LOSS_STREAK_ACTION,
                              LOSS_STREAK_REDUCE_PCT, LOSS_STREAK_PAUSE_SEC)

last_rearm_ts: Dict[str, float] = {'LONG':0.0,'SHORT':0.0}
entry_ts: Dict[str, float] = {'LONG':0.0,'SHORT':0.0}
pyramid_count: Dict[str,int] = {'LONG':0,'SHORT':0}
active_trades: Dict[str, dict] = {'LONG':None, 'SHORT':None}
loss_streak = 0

def _append_trade_log(row: dict):
    write_header = not os.path.exists(TRADE_LOG_FILE)
    try:
        with open(TRADE_LOG_FILE, 'a', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=list(row.keys()))
            if write_header: writer.writeheader()
            writer.writerow(row)
    except Exception as e:
        print('[WARN] trade log failed:', e)

def get_position_side_amt(client, symbol: str, side: str) -> Tuple[Decimal, Decimal]:
    pos = client.futures_position_information(symbol=symbol)
    for p in pos:
        amt = d(p.get('positionAmt','0'))
        entry = d(p.get('entryPrice','0'))
        ps = p.get('positionSide') or ('LONG' if amt>0 else 'SHORT')
        if side=='LONG' and ps=='LONG' and amt>0: return amt, entry
        if side=='SHORT' and ps=='SHORT' and amt<0: return amt, entry
    return Decimal('0'), Decimal('0')

def can_open_new_side(client, symbol: str, side: str) -> bool:
    amt, _ = get_position_side_amt(client, symbol, side)
    return (amt == 0)

def place_entry_market(client, symbol: str, direction: str, qty: Decimal, hedge_mode: bool):
    params = dict(symbol=symbol,
                  side=SIDE_BUY if direction=='BUY' else SIDE_SELL,
                  type=FUTURE_ORDER_TYPE_MARKET,
                  quantity=str(qty))
    if hedge_mode:
        params['positionSide'] = 'LONG' if direction=='BUY' else 'SHORT'
    print(f"[ENTRY] {direction} qty={qty}")
    res = retry(lambda: client.futures_create_order(**params), on_error=lambda e,i: print('[WARN] entry attempt',i,e))
    # record active trade for simple post-exit logging
    try:
        mark = d(client.futures_mark_price(symbol=symbol)['markPrice'])
        side = 'LONG' if direction=='BUY' else 'SHORT'
        active_trades[side] = {'entry_ts': time.time(), 'qty': d(qty), 'entry_price': mark, 'side': side}
    except Exception:
        pass
    return res

def place_brackets(client, symbol: str, side: str, entry_price: Decimal, tp_pct: Decimal, sl_pct: Decimal, filters, hedge_mode: bool):
    tick = filters['tick']
    if side=='LONG':
        tp_price = (entry_price*(Decimal('1')+tp_pct/Decimal('100'))).quantize(tick)
        sl_price = (entry_price*(Decimal('1')-sl_pct/Decimal('100'))).quantize(tick)
        exit_side = SIDE_SELL
    else:
        tp_price = (entry_price*(Decimal('1')-tp_pct/Decimal('100'))).quantize(tick)
        sl_price = (entry_price*(Decimal('1')+sl_pct/Decimal('100'))).quantize(tick)
        exit_side = SIDE_BUY

    tp = dict(symbol=symbol, side=exit_side, type=FUTURE_ORDER_TYPE_TAKE_PROFIT_MARKET,
              stopPrice=str(tp_price), closePosition=True, workingType='CONTRACT_PRICE')
    sl = dict(symbol=symbol, side=exit_side, type=FUTURE_ORDER_TYPE_STOP_MARKET,
              stopPrice=str(sl_price), closePosition=True, workingType='CONTRACT_PRICE')
    if hedge_mode:
        tp['positionSide'] = side; sl['positionSide'] = side

    tp_res = retry(lambda: client.futures_create_order(**tp), on_error=lambda e,i: print('[WARN] tp attempt',i,e))
    sl_res = retry(lambda: client.futures_create_order(**sl), on_error=lambda e,i: print('[WARN] sl attempt',i,e))
    print(f"[TP/SL] {side} TP={tp['stopPrice']} SL={sl['stopPrice']}")
    return tp_res, sl_res

def cancel_side_brackets(client, symbol: str, side: str):
    orders = retry(lambda: client.futures_get_open_orders(symbol=symbol), on_error=lambda e,i: print('[WARN] fetch orders',i,e))
    for o in orders:
        typ = o.get('type'); ps = o.get('positionSide')
        if ps and ps != side: continue
        if typ in ('TAKE_PROFIT_MARKET','STOP_MARKET','TAKE_PROFIT','STOP'):
            try:
                retry(lambda: client.futures_cancel_order(symbol=symbol, orderId=o['orderId']), on_error=lambda e,i: print('[WARN] cancel attempt',i,e))
            except Exception as e:
                print('[WARN] cancel:', e)

def calc_atr_sl_tp(entry_price: Decimal, atr: Decimal, side: str):
    if atr is None or atr == 0:
        return d(BASE_SL_PCT), d(BASE_TP_PCT), Decimal('0')
    atr = d(atr)
    k = Decimal('1.0')
    sl_distance = atr * k
    sl_pct = (sl_distance / entry_price) * Decimal('100')
    if sl_pct < d(BASE_SL_PCT):
        sl_pct = d(BASE_SL_PCT)
        sl_distance = entry_price * sl_pct / Decimal('100')
    tp_extra = (atr / entry_price) * Decimal('100') * Decimal('1.2')
    tp_pct = d(BASE_TP_PCT) + tp_extra
    if tp_pct > Decimal('10'):
        tp_pct = Decimal('10')
    return d(sl_pct), d(tp_pct), d(sl_distance)

def maybe_micro_tp(client, symbol: str, side: str, amt: Decimal, entry: Decimal, hedge_mode: bool):
    if amt == 0 or entry == 0: return False
    ts = entry_ts.get(side,0.0)
    if ts == 0.0: return False
    held_minutes = (time.time() - ts)/60.0
    if held_minutes < MICRO_TP_TRIGGER_MINUTES: return False
    try:
        mark = d(client.futures_mark_price(symbol=symbol)['markPrice'])
    except Exception:
        return False
    if side == 'LONG':
        unreal_pct = (mark - entry)/entry * Decimal('100')
    else:
        unreal_pct = (entry - mark)/entry * Decimal('100')
    if unreal_pct >= d(MICRO_TP_PCT):
        close_side = SIDE_SELL if side=='LONG' else SIDE_BUY
        params = dict(symbol=symbol, side=close_side, type=FUTURE_ORDER_TYPE_MARKET, closePosition=True)
        if hedge_mode: params['positionSide'] = side
        try:
            print(f"[MICRO-TP] closing {side} small profit {unreal_pct:.3f}% after {held_minutes:.1f}m")
            retry(lambda: client.futures_create_order(**params), on_error=lambda e,i: print('[WARN] micro-tp attempt',i,e))
            entry_ts[side] = 0.0; pyramid_count[side] = 0
            # treat as closed trade -> log exit
            _handle_trade_exit(client, symbol, side, mark)
            return True
        except Exception as e:
            print('[WARN] micro-tp failed:', e)
    return False

def _handle_trade_exit(client, symbol, side, exit_price):
    global loss_streak
    at = active_trades.get(side)
    if not at:
        return
    try:
        entry_price = d(at.get('entry_price',0))
        qty = d(at.get('qty',0))
        pnl = (exit_price - entry_price)/entry_price * Decimal('100') if side=='LONG' else (entry_price - exit_price)/entry_price * Decimal('100')
        row = {'ts': int(time.time()), 'side': side, 'entry_price': str(entry_price), 'exit_price': str(exit_price), 'qty': str(qty), 'pnl_pct': float(pnl)}
        _append_trade_log(row)
        # update loss streak
        if pnl < 0:
            loss_streak += 1
        else:
            loss_streak = 0
        active_trades[side] = None
    except Exception as e:
        print('[WARN] handle exit failed', e)

def maybe_rearm_adaptive(client, symbol: str, side: str, entry: Decimal, df, filters, hedge_mode: bool):
    now = time.time()
    if now - last_rearm_ts[side] < REARM_COOLDOWN_SEC: return
    last = df.iloc[-1]
    mark = d(last['close'])
    atr = d(last['atr']) if not pd.isna(last['atr']) else d(0)
    if atr == 0: return
    moved = (mark - entry) if side=='LONG' else (entry - mark)
    if moved <= 0: return
    if moved < d(ADAPT_TRIGGER_ATR) * atr: return
    try:
        cancel_side_brackets(client, symbol, side)
    except Exception as e:
        print('[WARN] cancel brackets:', e)
    new_tp_pct = d(BASE_TP_PCT) * d(TP_EXPAND_FACTOR)
    new_sl_pct = max(Decimal('0.05'), d(TRAIL_SL_LOCK_PCT))
    place_brackets(client, symbol, side, entry, d(new_tp_pct), d(new_sl_pct), filters, hedge_mode)
    last_rearm_ts[side] = now
    print(f"[ADAPT] {side} expanded TP to {float(new_tp_pct):.2f}% & trailed SL to {float(new_sl_pct):.2f}%")
