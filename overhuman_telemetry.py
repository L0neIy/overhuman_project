import os, csv, time
from overhuman_config import TELEMETRY_FILE, TARGET_MIN_EQUITY
from overhuman_execution import pyramid_count
from overhuman_risk import account_equity

metrics = {'trades':0, 'entries':0, 'skips':0}

def append_telemetry(client):
    try:
        equity = float(account_equity(client))
    except Exception:
        equity = float(TARGET_MIN_EQUITY)
    row = {'ts': int(time.time()), 'equity': equity, 'entries': metrics['entries'], 'trades': metrics['trades'], 'skips': metrics['skips'], 'pyramid_long': pyramid_count['LONG'], 'pyramid_short': pyramid_count['SHORT']}
    write_header = not os.path.exists(TELEMETRY_FILE)
    try:
        with open(TELEMETRY_FILE, 'a', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=list(row.keys()))
            if write_header: writer.writeheader()
            writer.writerow(row)
    except Exception as e:
        print('[WARN] telemetry write failed:', e)
