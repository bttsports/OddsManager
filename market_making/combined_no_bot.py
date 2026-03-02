"""
Combined No Spread bot for Kalshi.
Buys No at median bid-ask pricing, split from max_combined across included stakes.
Uses median of each market's No bid-ask; averages across stakes. Offers at target
prices summing to max_combined. For half-cent rounding, assigns higher price to
the side with more liquidity. For 2-outcome markets primarily.
Run: python -m market_making.combined_no_bot
"""
from __future__ import annotations

import json
import os
import signal
import sys
import time
import urllib.request
from typing import Any, Optional

# Ensure project root is on path
_script_dir = os.path.dirname(os.path.abspath(__file__))
_project_root = os.path.dirname(_script_dir)
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

os.chdir(_project_root)

# Load .env
try:
    from dotenv import load_dotenv

    load_dotenv(os.path.join(_project_root, ".env"))
except ImportError:
    pass

from betting_outs.kalshi.kalshi import get_client

DEFAULT_CONFIG_PATH = os.path.join(_script_dir, "combined_no_config.json")


def load_config(path: Optional[str] = None) -> dict:
    """Load config from JSON file."""
    p = path or os.environ.get("COMBINED_NO_CONFIG") or DEFAULT_CONFIG_PATH
    with open(p, "r") as f:
        return json.load(f)


def send_alert(url: Optional[str], reason: str, details: Optional[dict] = None) -> None:
    """POST alert to webhook and print."""
    print(f"ALERT: {reason}")
    if url:
        try:
            payload = {"reason": reason}
            if details:
                payload.update(details)
            req = urllib.request.Request(
                url,
                data=json.dumps(payload).encode(),
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            urllib.request.urlopen(req, timeout=5)
        except Exception as e:
            print(f"Alert webhook failed: {e}")


def _get_no_bid_ask(client: Any, ticker: str) -> Optional[tuple[int, int, float, dict[int, int]]]:
    """
    Fetch orderbook and return (no_bid, no_ask, median, no_price_to_qty).
    No ask = 100 - best_yes_bid. Median = (bid + ask) / 2.
    no_price_to_qty = {price: qty} from the no orderbook for liquidity lookups.
    Returns None if orderbook empty/failed.
    """
    try:
        data = client.get_orderbook(ticker)
        ob = data.get("orderbook") or {}
        yes_bids = ob.get("yes") or []
        no_bids = ob.get("no") or []
        if not yes_bids or not no_bids:
            return None
        best_yes_bid = int(yes_bids[-1][0])
        best_no_bid = int(no_bids[-1][0])
        best_no_ask = 100 - best_yes_bid
        median = (best_no_bid + best_no_ask) / 2.0
        price_to_qty: dict[int, int] = {int(p): int(q) for p, q in no_bids}
        return (
            max(1, min(99, best_no_bid)),
            max(1, min(99, best_no_ask)),
            median,
            price_to_qty,
        )
    except Exception as e:
        print(f"Orderbook fetch failed for {ticker}: {e}")
        return None


def compute_offer_prices(
    tickers: list[str],
    bid_ask_data: dict[str, tuple[int, int, float, dict[int, int]]],
    max_combined: int,
) -> dict[str, int]:
    """
    Compute offer price per ticker. Target sum = max_combined.
    Split evenly. If half-cent (e.g. 48.5 for 2 tickers), assign the higher
    price (49) to the ticker with more liquidity at that price.
    """
    n = len(tickers)
    if n == 0:
        return {}
    base = max_combined // n
    remainder = max_combined - base * n

    if remainder == 0:
        return {t: base for t in tickers}

    # remainder > 0: assign base+1 to 'remainder' tickers.
    # Tiebreak: assign base+1 to tickers with more liquidity at base+1
    higher_price = base + 1

    def liquidity_at(ticker: str, price: int) -> int:
        d = bid_ask_data.get(ticker)
        if not d:
            return 0
        _, _, _, price_to_qty = d
        return price_to_qty.get(price, 0)

    sorted_tickers = sorted(
        tickers,
        key=lambda t: liquidity_at(t, higher_price),
        reverse=True,
    )
    result: dict[str, int] = {}
    for i, t in enumerate(sorted_tickers):
        result[t] = higher_price if i < remainder else base
    return result


def run(config: dict, env: Optional[str] = None) -> None:
    """Run the combined No spread loop. KALSHI_ENV (from env) overrides config env."""
    env = (os.environ.get("KALSHI_ENV") or env or config.get("env") or "DEMO").upper()
    event_ticker = config.get("event_ticker") or ""
    tickers = config.get("tickers") or []
    max_combined = int(config.get("max_combined") or 99)
    shares = int(config.get("shares") or 10)
    check_interval = int(config.get("check_interval_sec") or 5)
    alert_url = config.get("alert_webhook_url")

    if not tickers:
        print("No tickers in config. Exiting.")
        return

    if shares < 1:
        print("Shares must be >= 1. Exiting.")
        return

    client = get_client(env)
    our_order_ids: set[str] = set()
    orders_up = False

    def shutdown_cancel_all() -> None:
        """On SIGTERM (systemd stop): batch cancel all resting combined_no_ orders for this event."""
        if not event_ticker:
            return
        try:
            resp = client.get_orders(limit=200, status="resting", event_ticker=event_ticker)
            orders = resp.get("orders") or []
            our_ids = [
                str(o.get("order_id") or o.get("id") or "")
                for o in orders
                if (o.get("client_order_id") or "").strip().startswith("combined_no_")
            ]
            if our_ids:
                client.batch_cancel_orders(our_ids)
                print(f"Shutdown: batch cancelled {len(our_ids)} order(s)")
            else:
                print("Shutdown: no resting orders to cancel")
        except Exception as e:
            print(f"Shutdown cancel failed: {e}")
        sys.exit(0)

    def _on_sigterm(signum: int, frame: Any) -> None:
        shutdown_cancel_all()

    signal.signal(signal.SIGTERM, _on_sigterm)

    while True:
        try:
            # Fetch orderbooks: No bid, No ask, median per ticker
            bid_ask_data: dict[str, tuple[int, int, float, dict[int, int]]] = {}
            for ticker in tickers:
                row = _get_no_bid_ask(client, ticker)
                if row is not None:
                    bid_ask_data[ticker] = row
                else:
                    # Conservative: treat as expensive (high median)
                    bid_ask_data[ticker] = (99, 99, 99.0, {})

            if len(bid_ask_data) < len(tickers):
                # Some failed; skip this cycle
                time.sleep(check_interval)
                continue

            # Condition: use combined best No bids (not median)
            combined_no_bids = sum(d[0] for d in bid_ask_data.values())
            combined_median = sum(d[2] for d in bid_ask_data.values())

            if combined_no_bids >= max_combined:
                # Condition failed: leave orders as-is (no cancel). Won't refill if filled.
                print(
                    f"Condition not met (combined_no_bids={combined_no_bids} >= {max_combined}). "
                    "Leaving resting orders; no refill if filled."
                )
                if alert_url:
                    send_alert(
                        alert_url,
                        "combined_no_condition_failed",
                        {
                            "combined_no_bids": combined_no_bids,
                            "max_combined": max_combined,
                        },
                    )
                orders_up = False
            else:
                # Condition passes: compute offer prices, ensure full shares resting
                offer_prices = compute_offer_prices(tickers, bid_ask_data, max_combined)
                target_sum = sum(offer_prices.values())

                our_resting: dict[str, tuple[str, int]] = {}  # ticker -> (order_id, remaining_count)
                if event_ticker:
                    try:
                        resp = client.get_orders(limit=200, status="resting", event_ticker=event_ticker)
                        for o in resp.get("orders") or []:
                            cid = (o.get("client_order_id") or "").strip()
                            if not cid.startswith("combined_no_"):
                                continue
                            ticker = (o.get("ticker") or "").strip()
                            oid = str(o.get("order_id") or o.get("id") or "")
                            remaining = int(o.get("remaining_count") or 0)
                            if ticker and oid:
                                our_resting[ticker] = (oid, remaining)
                    except Exception as e:
                        print(f"Could not fetch resting orders: {e}")

                needs_refill = [
                    t for t in tickers
                    if t not in our_resting or our_resting[t][1] < shares
                ]

                if needs_refill:
                    for ticker in needs_refill:
                        if ticker in our_resting:
                            oid, rem = our_resting[ticker]
                            try:
                                client.cancel_order(oid)
                                our_order_ids.discard(oid)
                                if rem < shares:
                                    print(f"Refill {ticker}: had {rem}, replacing with {shares}")
                            except Exception as e:
                                print(f"Cancel {oid}: {e}")

                    for ticker in needs_refill:
                        no_price = offer_prices.get(ticker, max_combined // len(tickers))
                        try:
                            r = client.create_order(
                                ticker=ticker,
                                action="buy",
                                side="no",
                                count=shares,
                                no_price=no_price,
                                client_order_id=f"combined_no_{ticker}",
                            )
                            oid = r.get("order", {}).get("order_id") or r.get("order_id")
                            if oid:
                                our_order_ids.add(str(oid))
                            print(
                                f"Placed buy No {ticker} @ {no_price}c x{shares} "
                                f"(median_sum={combined_median:.1f}, target_sum={target_sum})"
                            )
                        except Exception as e:
                            print(f"Place buy No failed {ticker}: {e}")
                    orders_up = True

        except Exception as e:
            print(f"Loop error: {e}")
            if alert_url:
                send_alert(alert_url, "combined_no_loop_error", {"error": str(e)})

        time.sleep(check_interval)


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--config", help="Path to config JSON")
    args = parser.parse_args()
    config = load_config(args.config) if args.config else load_config()
    run(config)
