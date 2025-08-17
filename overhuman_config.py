from decimal import Decimal
from utils import d

# ========= CONFIG (Testnet-first, safe defaults) =========
TESTNET       = True
SYMBOL        = "BTCUSDT"
LEVERAGE      = 10
HEDGE_MODE    = True
INTERVAL      = "1m"
LOOP_SECONDS  = 7  # FAST+PRECISION (rate limit aware)

# --- Capital & Risk ---
TARGET_MIN_EQUITY  = Decimal("1000")
RISK_PER_TRADE_PCT = Decimal("0.5")    # base % risk per trade (can be adjusted)
MIN_RISK_PCT       = Decimal("0.1")    # smallest allowed risk %
MAX_RISK_PCT       = Decimal("3.0")    # largest allowed risk % for a single trade

# Baseline SL/TP (percent of price)
BASE_SL_PCT = Decimal("0.35")   # 0.35% default stop-loss (used as fallback if ATR unavailable)
BASE_TP_PCT = Decimal("0.60")   # 0.60% default take-profit (base target)

# --- Adaptive Engine ---
ATR_WINDOW            = 10
ADAPT_TRIGGER_ATR     = Decimal("0.45")
TP_EXPAND_FACTOR      = Decimal("1.6")
TRAIL_SL_LOCK_PCT     = Decimal("0.2")
REARM_COOLDOWN_SEC    = 8

# --- Filters / Precision ---
VOL_WINDOW       = 12
MIN_VOL_PCT      = Decimal("0.045")
VOL_BOOST_FACTOR = Decimal("1.10")
DOJI_ATR_RATIO   = Decimal("0.12")

# --- Multi-Timeframe ---
HTF_INTERVALS = ["3m","5m","15m"]
HTF_EMA_FAST = 8
HTF_EMA_SLOW = 21
HTF_EMA_CONFIRM = 50  # for 15m trend alignment (EMA50)

# ADX settings
ADX_PERIOD = 14
MIN_ADX = 18

# --- Bollinger ---
BB_WINDOW = 20
BB_WIDTH_MIN = Decimal("0.006")   # 0.6%

# --- Micro-TP & Pyramiding ---
MICRO_TP_TRIGGER_MINUTES = 12
MICRO_TP_PCT = Decimal("0.12")
ALLOW_PYRAMID = True
MAX_PYRAMID_LEVELS = 2
PYRAMID_MIN_MOMENTUM_ATR = Decimal("0.4")

# --- Telemetry ---
TELEMETRY_INTERVAL_SEC = 1800
TELEMETRY_FILE = "telemetry.csv"
TRADE_LOG_FILE = "trade_log.csv"

# --- Loss streak protection ---
LOSS_STREAK_LIMIT = 3         # after N losing trades take action
LOSS_STREAK_ACTION = "reduce" # "reduce" or "pause"
LOSS_STREAK_REDUCE_PCT = Decimal("0.5")  # reduce risk by factor (0.5=half)
LOSS_STREAK_PAUSE_SEC = 600   # pause for 10 minutes if action == "pause"

# --- Confidence sizing bounds ---
CONFIDENCE_MIN = Decimal("0.6")
CONFIDENCE_MAX = Decimal("1.6")
HTF_VOTE_THRESHOLD = 1  # require at least this absolute vote count if >=2 HTFs available

# Safety toggles (fine-tune as you collect testnet data)
ENABLE_DYNAMIC_SIZING = True
ENABLE_LOSS_STREAK_PROTECTION = True

# --- Multi-Symbol ---
SYMBOLS = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT"]
MAX_OPEN_POSITIONS = 2   # เริ่มแบบคุมความเสี่ยง (ค่อยเพิ่มเมื่อทุนโต)

# --- Afterburner ---
AFTERBURNER_ENABLED = True
AFTERBURNER_SCAN_FACTOR = 3
AFTERBURNER_MAX_DURATION_SEC = 300

# --- ACE-Z Hunter ---
ACEZ_ENABLED = True
ACEZ_WINDOW_SEC = 45
ACEZ_DROP_PCT = 1.0
ACEZ_SPIKE_PCT = 1.0
ACEZ_COOLDOWN_SEC = 120
ACEZ_QTY_FACTOR = d('0.5')
ACEZ_TP_SL_ATR_MULT = (d('0.6'), d('0.8'))

# End of config
