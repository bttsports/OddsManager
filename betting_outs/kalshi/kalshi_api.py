"""
Local HTTP API for the desktop app to call Kalshi.
Run from project root: python betting_outs/kalshi/kalshi_api.py
Listens on http://127.0.0.1:8766. Loads .env from project root (KALSHI_API_KEY, KALSHI_PRIVATE_KEY_PATH).
All routes accept ?env=demo or ?env=prod (default demo).
"""
import os
import sys

# Load .env from project root so KALSHI_API_KEY and KALSHI_PRIVATE_KEY_PATH are set
_here = os.path.dirname(os.path.abspath(__file__))
_project_root = os.path.dirname(os.path.dirname(_here))
_env_path = os.path.join(_project_root, ".env")
if os.path.isfile(_env_path):
    try:
        from dotenv import load_dotenv
        load_dotenv(_env_path)
    except ImportError:
        pass
if _here not in sys.path:
    sys.path.insert(0, _here)

from urllib.parse import urlencode

import requests
from flask import Flask, request, jsonify

app = Flask(__name__)

KALSHI_BASE_URL = {"DEMO": "https://demo-api.kalshi.co", "PROD": "https://api.elections.kalshi.com"}
MARKETS_PATH = "/trade-api/v2/markets"

KALSHI_PORT = int(os.getenv("KALSHI_API_PORT", "8766"))


def env_from_request():
    e = (request.args.get("env") or "demo").strip().upper()
    return "DEMO" if e == "DEMO" else "PROD"


def get_client():
    from kalshi import get_client
    return get_client(env_from_request())


@app.route("/health")
def health():
    return jsonify({"ok": True})


@app.route("/balance")
def balance():
    try:
        client = get_client()
        data = client.get_balance()
        return jsonify(data)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/exchange-status")
def exchange_status():
    try:
        client = get_client()
        data = client.get_exchange_status()
        return jsonify(data)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/orders")
def orders():
    try:
        client = get_client()
        limit = request.args.get("limit", type=int)
        cursor = request.args.get("cursor")
        status = request.args.get("status")
        data = client.get_orders(limit=limit, cursor=cursor, status=status)
        return jsonify(data)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/positions")
def positions():
    try:
        client = get_client()
        limit = request.args.get("limit", type=int)
        cursor = request.args.get("cursor")
        data = client.get_positions(limit=limit, cursor=cursor)
        return jsonify(data)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/markets")
def markets():
    """Call Kalshi markets API the same way as the working test_series.py: simple GET, no auth, preserve ticker case."""
    try:
        env = env_from_request()
        base = KALSHI_BASE_URL.get(env, KALSHI_BASE_URL["DEMO"])
        # Match the working test script: do NOT force a limit param; let Kalshi defaults apply.
        url_params = {}
        for key in ("limit", "cursor", "status", "event_ticker", "series_ticker", "tickers"):
            v = request.args.get(key)
            if v is not None and str(v).strip():
                url_params[key] = str(v).strip()
        request_url = base + MARKETS_PATH + "?" + urlencode(url_params)
        resp = requests.get(request_url, timeout=15)
        resp.raise_for_status()
        data = resp.json()
        data["request_url"] = request_url
        return jsonify(data)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/market-reciprocal")
def market_reciprocal():
    """If the given ticker's event has exactly 2 markets, return the other market's ticker (for binary pairs like Team A vs Team B). Else 404."""
    try:
        ticker = (request.args.get("ticker") or "").strip()
        if not ticker:
            return jsonify({"error": "ticker required"}), 400
        env = env_from_request()
        base = KALSHI_BASE_URL.get(env, KALSHI_BASE_URL["DEMO"])
        # Get this market to learn event_ticker (no auth)
        url_one = base + MARKETS_PATH + "?" + urlencode({"tickers": ticker})
        resp = requests.get(url_one, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        markets_one = data.get("markets") or []
        if not markets_one:
            return jsonify({"error": "Market not found", "ticker": ticker}), 404
        event_ticker = (markets_one[0].get("event_ticker") or "").strip()
        if not event_ticker:
            return jsonify({"error": "Market has no event_ticker", "ticker": ticker}), 404
        # Get all markets for this event
        url_event = base + MARKETS_PATH + "?" + urlencode({"event_ticker": event_ticker})
        resp2 = requests.get(url_event, timeout=10)
        resp2.raise_for_status()
        data2 = resp2.json()
        event_markets = data2.get("markets") or []
        if len(event_markets) != 2:
            return jsonify({"error": "Event does not have exactly 2 markets", "event_ticker": event_ticker, "count": len(event_markets)}), 404
        ticker_norm = ticker.strip().upper()
        other = next((m for m in event_markets if ((m.get("ticker") or "").strip().upper() != ticker_norm)), None)
        if not other:
            return jsonify({"error": "Other market not found"}), 404
        reciprocal_ticker = (other.get("ticker") or "").strip()
        return jsonify({"reciprocal_ticker": reciprocal_ticker, "event_ticker": event_ticker})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/order", methods=["POST"])
def create_order():
    try:
        client = get_client()
        body = request.get_json() or {}
        ticker = body.get("ticker")
        action = body.get("action", "buy")
        side = body.get("side", "yes")
        count = int(body.get("count", 0))
        order_type = body.get("type", "limit")
        yes_price = body.get("yes_price")
        no_price = body.get("no_price")
        client_order_id = body.get("client_order_id")
        time_in_force = body.get("time_in_force")
        expiration_ts = body.get("expiration_ts")
        if not ticker or count < 1:
            return jsonify({"error": "ticker and count required"}), 400
        if yes_price is not None:
            yes_price = int(yes_price)
        if no_price is not None:
            no_price = int(no_price)
        requested_expiration = body.get("expiration_ts")
        if expiration_ts is not None:
            # REST Create Order docs: expiration_ts is an integer; field examples (and user tests)
            # indicate seconds, not milliseconds. For \"Specific time\" and \"At event start\" we
            # send expiration_ts in seconds and intentionally omit time_in_force so the backend
            # interprets it using its default behavior (currently appears as GTC).
            expiration_ts = int(expiration_ts)
            # Do NOT override time_in_force here; leave whatever the caller sent (usually None).
        elif requested_expiration is not None and requested_expiration != "":
            return jsonify({"error": "Expiration at specific time was requested but could not be applied. Request aborted."}), 400
        data = client.create_order(
            ticker=ticker,
            action=action,
            side=side,
            count=count,
            order_type=order_type,
            yes_price=yes_price,
            no_price=no_price,
            client_order_id=client_order_id,
            time_in_force=time_in_force,
            expiration_ts=expiration_ts,
        )
        return jsonify(data)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/order/<order_id>", methods=["DELETE"])
def cancel_order(order_id):
    try:
        client = get_client()
        data = client.cancel_order(order_id)
        return jsonify(data)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/orders/batch", methods=["POST"])
def batch_place_orders():
    """Place multiple orders sequentially with rate limiting. Body: { orders: [{ ticker, side, count, yes_price?, no_price?, time_in_force?, expiration_ts? }, ...] }. Max 10 per request."""
    try:
        client = get_client()
        body = request.get_json() or {}
        orders = list(body.get("orders") or [])
        if not isinstance(orders, list):
            return jsonify({"error": "orders must be a list"}), 400
        env = env_from_request()
        for o in orders:
            if o.get("expiration_ts") is not None and isinstance(o.get("expiration_ts"), (int, float)):
                # Normalize to an int seconds value; do not set time_in_force for timed expirations.
                o["expiration_ts"] = int(o["expiration_ts"])
        data = client.batch_place_orders(orders)
        return jsonify(data)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=KALSHI_PORT, debug=False, use_reloader=False)
