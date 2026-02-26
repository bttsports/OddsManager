import os
import sys
import uuid
import datetime
from zoneinfo import ZoneInfo

# Ensure project root is on sys.path so we can import betting_outs.*
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from betting_outs.kalshi.kalshi import (
    KalshiHttpClient,
    load_private_key,
    _default_private_key_path,
    KALSHI_API_KEY,
)


def build_expiration_s_for_today_6pm_et() -> int:
    """Compute today's 6:00 PM America/New_York in Unix seconds since epoch (UTC)."""
    now_et = datetime.datetime.now(ZoneInfo("America/New_York"))
    exp_et = now_et.replace(hour=18, minute=0, second=0, microsecond=0)
    # If it's already past 6pm ET, this will be in the past; for this one-off test we accept that.
    exp_utc = exp_et.astimezone(datetime.timezone.utc)
    return int(exp_utc.timestamp())


def main() -> None:
    if not KALSHI_API_KEY:
        raise RuntimeError("KALSHI_API_KEY is not set in the environment / .env")

    private_key_path = _default_private_key_path()
    private_key = load_private_key(private_key_path)

    client = KalshiHttpClient(
        key_id=KALSHI_API_KEY,
        private_key=private_key,
        environment="PROD",
    )

    expiration_ts_s = build_expiration_s_for_today_6pm_et()

    ticker = "KXMAINEHOUSE94SPECIAL-26FEB24-SHAR-P65"

    print(f"  ticker={ticker}")
    print("  side=yes, action=buy, count=1, type=limit, yes_price=33")
    print(f"  expiration_ts(s)={expiration_ts_s}")

    res = client.create_order(
        ticker=ticker,
        action="buy",
        side="yes",
        count=1,
        order_type="limit",
        yes_price=33,
        no_price=None,
        client_order_id=str(uuid.uuid4()),
        expiration_ts=expiration_ts_s,
    )

    print("Create order response:")
    print(res)


if __name__ == "__main__":
    main()

