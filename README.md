# OverHuman Commander — ULTRA (Decimal-safe, Upgraded)
Upgraded version that fixes Decimal/float errors and adds:
- Multi-timeframe confirmation and HTF vote confidence
- Volatility & ATR-based filters
- Dynamic position sizing (confidence-based)
- Loss-streak protection (auto-reduce risk / pause)
- Robust retry & auto-reconnect wrappers
- Trade logging (entry/exit records)
- Decimal-safe arithmetic everywhere

**Quick start**:
1. `pip install -r requirements.txt`
2. Copy `.env.sample` -> `.env` and fill Testnet keys.
3. `python overhuman_commander_ultra.py` (testnet first)
