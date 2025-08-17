import os, time, random
from decimal import Decimal, ROUND_DOWN, getcontext
from typing import Any, Callable
from dotenv import load_dotenv
from binance.client import Client

getcontext().prec = 18

def load_env_overrides(cfg):
    load_dotenv(override=True)
    cfg.TESTNET    = _env_bool("TESTNET", cfg.TESTNET)
    cfg.SYMBOL     = os.getenv("SYMBOL", cfg.SYMBOL)
    cfg.LEVERAGE   = int(os.getenv("LEVERAGE", cfg.LEVERAGE))
    cfg.HEDGE_MODE = _env_bool("HEDGE_MODE", cfg.HEDGE_MODE)
    cfg.INTERVAL   = os.getenv("INTERVAL", cfg.INTERVAL)
    return cfg

def _env_bool(key: str, default: bool) -> bool:
    v = os.getenv(key)
    if v is None: return default
    return str(v).strip().lower() in ("1","true","yes","y","on")

def get_api_keys():
    from dotenv import dotenv_values
    env = dotenv_values()
    key = env.get("API_KEY") or os.getenv("API_KEY")
    sec = env.get("API_SECRET") or os.getenv("API_SECRET")
    if not key or not sec:
        raise RuntimeError("Missing API_KEY/API_SECRET. Fill them in .env")
    return key, sec

def setup_client(TESTNET: bool):
    key, sec = get_api_keys()
    return Client(key, sec, testnet=TESTNET)

def retry(op: Callable, attempts=5, base_delay=0.8, jitter=0.2, on_error: Callable[[Exception,int],None]=None):
    for i in range(attempts):
        try:
            return op()
        except Exception as e:
            if on_error: on_error(e, i+1)
            if i == attempts - 1: raise
            delay = base_delay * (2 ** i) + random.uniform(0, jitter)
            time.sleep(delay)

def round_step(qty: Decimal, step: Decimal) -> Decimal:
    q = (qty / step).to_integral_value(rounding=ROUND_DOWN) * step
    return q.quantize(step)

def d(x) -> Decimal:
    """Convert various numeric types to Decimal safely."""
    if x is None:
        return Decimal("0")
    if isinstance(x, Decimal):
        return x
    try:
        # handle numpy types and floats
        return Decimal(str(x))
    except Exception:
        return Decimal("0")

from decimal import Decimal, ROUND_DOWN, ROUND_UP

def adjust_qty_step(qty: Decimal, step: Decimal, min_notional: Decimal = None, mark: Decimal = None) -> Decimal:
    """
    ปรับ qty ให้ปัด step size และผ่าน min_notional (ถ้าให้มา)
    qty : Decimal จำนวนเหรียญที่จะสั่ง
    step : Decimal step size ของเหรียญ
    min_notional : Decimal มูลค่าขั้นต่ำของออเดอร์ (optional)
    mark : Decimal ราคาล่าสุด (optional)
    """
    qty = qty.quantize(step, rounding=ROUND_DOWN)
    if min_notional is not None and mark is not None:
        if qty * mark < min_notional:
            qty = (min_notional / mark).quantize(step, rounding=ROUND_UP)
    return qty

