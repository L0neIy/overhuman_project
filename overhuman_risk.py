from decimal import Decimal
from typing import Dict
from utils import d, round_step
from overhuman_config import (TARGET_MIN_EQUITY, RISK_PER_TRADE_PCT, BASE_SL_PCT,
                              MAX_RISK_PCT, MIN_RISK_PCT, CONFIDENCE_MIN, CONFIDENCE_MAX)

def account_equity(client) -> Decimal:
    try:
        bals = client.futures_account_balance()
        for b in bals:
            if b.get('asset') in ('USDT','FDUSD','BUSD'):
                return d(b.get('balance','0'))
    except Exception:
        pass
    return TARGET_MIN_EQUITY

def compute_risk_based_qty(client, filters: Dict, sl_distance: Decimal, symbol: str, confidence: Decimal) -> Decimal:
    """Compute qty using base risk scaled by confidence (Decimal). Ensures result obeys min/max risk caps."""
    equity = account_equity(client)
    base_risk_pct = d(RISK_PER_TRADE_PCT)
    # scale risk by confidence (bounded)
    conf = min(max(confidence, CONFIDENCE_MIN), CONFIDENCE_MAX)
    risk_pct = base_risk_pct * conf
    # clamp to min/max
    if risk_pct < d(MIN_RISK_PCT):
        risk_pct = d(MIN_RISK_PCT)
    if risk_pct > d(MAX_RISK_PCT):
        risk_pct = d(MAX_RISK_PCT)
    risk_cap = equity * (risk_pct/Decimal('100'))
    price = d(client.futures_mark_price(symbol=symbol)['markPrice'])
    if sl_distance and sl_distance > 0:
        sl_pct = (sl_distance / price) * Decimal('100')
        if sl_pct <= 0:
            sl_pct = d(BASE_SL_PCT)
        notional = risk_cap / (sl_pct/Decimal('100'))
    else:
        sl_pct = d(BASE_SL_PCT)
        notional = risk_cap / (sl_pct/Decimal('100'))
    notional_cap = equity * d(MAX_RISK_PCT)
    if notional > notional_cap:
        notional = notional_cap
    qty = round_step(notional/price, filters['step'])
    if qty < filters['min_qty']:
        qty = filters['min_qty']
    if qty*price < filters['min_notional']:
        qty = round_step(filters['min_notional']/price, filters['step'])
    return qty
