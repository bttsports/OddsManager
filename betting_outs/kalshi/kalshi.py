import base64
import os
import uuid
import requests
import websockets
import time
import json
from datetime import datetime, timedelta
from typing import Any, Dict, Optional

# Optional: load .env from project root when this module is run or imported from kalshi_api
try:
    from dotenv import load_dotenv
    _root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    _env = os.path.join(_root, ".env")
    if os.path.isfile(_env):
        load_dotenv(_env)
except ImportError:
    pass

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.backends import default_backend


KALSHI_API_KEY = os.getenv("KALSHI_API_KEY")


def _default_private_key_path() -> str:
    """If KALSHI_PRIVATE_KEY_PATH is not set, use tocotoucan.pem next to this file."""
    env_path = os.getenv("KALSHI_PRIVATE_KEY_PATH")
    if env_path and os.path.isfile(env_path):
        return env_path
    same_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "tocotoucan.pem")
    if os.path.isfile(same_dir):
        return same_dir
    if env_path:
        return env_path  # user set it but file missing; let load_private_key raise
    raise ValueError(
        "KALSHI_PRIVATE_KEY_PATH not set and tocotoucan.pem not found in betting_outs/kalshi. "
        "Set KALSHI_PRIVATE_KEY_PATH to your PEM path (e.g. full path to tocotoucan.pem)."
    )


def load_private_key(path):
    """Load PEM private key."""
    try:
        with open(path, "rb") as f:
            data = f.read()
        return serialization.load_pem_private_key(data, password=None, backend=default_backend())
    except Exception as e:
        raise RuntimeError(f"Failed to load private key: {e}")


class KalshiBaseClient:
    """Base client class for interacting with the Kalshi API."""
    def __init__(
        self,
        key_id: str,
        private_key: rsa.RSAPrivateKey,
        environment: str,
    ):
        """Initializes the client with the provided API key and private key.

        Args:
            key_id (str): Your Kalshi API key ID.
            private_key (rsa.RSAPrivateKey): Your RSA private key.
            environment (Environment): The API environment to use ("DEMO" or "PROD").
        """
        self.key_id = key_id
        self.private_key = private_key
        self.environment = environment
        self.last_api_call = datetime.now()

        if self.environment == "DEMO":
            self.HTTP_BASE_URL = "https://demo-api.kalshi.co"
            self.WS_BASE_URL = "wss://demo-api.kalshi.co"
        elif self.environment == "PROD":
            self.HTTP_BASE_URL = "https://api.elections.kalshi.com"
            self.WS_BASE_URL = "wss://api.elections.kalshi.com"
        else:
            raise ValueError("Invalid environment")

    def request_headers(self, method: str, path: str) -> Dict[str, Any]:
        """Generates the required authentication headers for API requests."""
        current_time_milliseconds = int(time.time() * 1000)
        timestamp_str = str(current_time_milliseconds)

        # Remove query params from path
        path_parts = path.split('?')

        msg_string = timestamp_str + method + path_parts[0]
        signature = self.sign_pss_text(msg_string)

        headers = {
            "Content-Type": "application/json",
            "KALSHI-ACCESS-KEY": self.key_id,
            "KALSHI-ACCESS-SIGNATURE": signature,
            "KALSHI-ACCESS-TIMESTAMP": timestamp_str,
        }
        return headers

    def sign_pss_text(self, text: str) -> str:
        """Signs the text using RSA-PSS and returns the base64 encoded signature."""
        message = text.encode('utf-8')
        try:
            signature = self.private_key.sign(
                message,
                padding.PSS(
                    mgf=padding.MGF1(hashes.SHA256()),
                    salt_length=padding.PSS.DIGEST_LENGTH
                ),
                hashes.SHA256()
            )
            return base64.b64encode(signature).decode('utf-8')
        except InvalidSignature as e:
            raise ValueError("RSA sign PSS failed") from e

class KalshiHttpClient(KalshiBaseClient):
    """Client for handling HTTP connections to the Kalshi API."""
    def __init__(
        self,
        key_id: str,
        private_key: rsa.RSAPrivateKey,
        environment: str = "DEMO",
    ):
        super().__init__(key_id, private_key, environment)
        self.host = self.HTTP_BASE_URL
        self.exchange_url = "/trade-api/v2/exchange"
        self.markets_url = "/trade-api/v2/markets"
        self.portfolio_url = "/trade-api/v2/portfolio"

    # Kalshi rate limits: Basic 20 read / 10 write per second. We throttle all calls to stay under write limit.
    RATE_LIMIT_MIN_INTERVAL_SEC = 0.12  # ~8 calls/sec max; no infinite loops or recursion.

    def rate_limit(self) -> None:
        """Enforce minimum interval between API calls. Never exceed account rate limit."""
        now = datetime.now()
        elapsed = (now - self.last_api_call).total_seconds()
        if elapsed < self.RATE_LIMIT_MIN_INTERVAL_SEC:
            time.sleep(self.RATE_LIMIT_MIN_INTERVAL_SEC - elapsed)
        self.last_api_call = datetime.now()

    def raise_if_bad_response(self, response: requests.Response) -> None:
        """Raises an HTTPError if the response status code indicates an error."""
        if response.status_code not in range(200, 299):
            response.raise_for_status()

    def post(self, path: str, body: dict) -> Any:
        """Performs an authenticated POST request to the Kalshi API."""
        self.rate_limit()
        response = requests.post(
            self.host + path,
            json=body,
            headers=self.request_headers("POST", path)
        )
        self.raise_if_bad_response(response)
        return response.json()

    def get(self, path: str, params: Dict[str, Any] = {}) -> Any:
        """Performs an authenticated GET request to the Kalshi API."""
        self.rate_limit()
        response = requests.get(
            self.host + path,
            headers=self.request_headers("GET", path),
            params=params
        )
        self.raise_if_bad_response(response)
        return response.json()

    def delete(self, path: str, params: Dict[str, Any] = {}) -> Any:
        """Performs an authenticated DELETE request to the Kalshi API."""
        self.rate_limit()
        response = requests.delete(
            self.host + path,
            headers=self.request_headers("DELETE", path),
            params=params
        )
        self.raise_if_bad_response(response)
        return response.json()

    def get_balance(self) -> Dict[str, Any]:
        """Retrieves the account balance."""
        return self.get(self.portfolio_url + '/balance')

    def get_exchange_status(self) -> Dict[str, Any]:
        """Retrieves the exchange status."""
        return self.get(self.exchange_url + "/status")

    def get_trades(
        self,
        ticker: Optional[str] = None,
        limit: Optional[int] = None,
        cursor: Optional[str] = None,
        max_ts: Optional[int] = None,
        min_ts: Optional[int] = None,
    ) -> Dict[str, Any]:
        """Retrieves trades based on provided filters."""
        params = {
            'ticker': ticker,
            'limit': limit,
            'cursor': cursor,
            'max_ts': max_ts,
            'min_ts': min_ts,
        }
        params = {k: v for k, v in params.items() if v is not None}
        return self.get(self.markets_url + '/trades', params=params)

    # Hard cap for batch order operations; no recursion or unbounded loops.
    MAX_BATCH_ORDERS = 10

    def get_markets(
        self,
        limit: Optional[int] = None,
        cursor: Optional[str] = None,
        status: Optional[str] = None,
        event_ticker: Optional[str] = None,
        series_ticker: Optional[str] = None,
        tickers: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Get markets. Use event_ticker for an event, series_ticker for a series, or tickers (comma-separated) for specific markets.
        status: open, closed, settled; omit for any. Tickers sent lowercase to match Kalshi URLs."""
        params = {
            'limit': min(limit or 200, 200),
            'cursor': cursor,
            'status': status,
            'event_ticker': event_ticker.lower() if event_ticker else None,
            'series_ticker': series_ticker.lower() if series_ticker else None,
            'tickers': tickers.lower() if tickers else None,
        }
        params = {k: v for k, v in params.items() if v is not None}
        return self.get(self.markets_url, params=params)

    def get_orders(
        self,
        limit: Optional[int] = None,
        cursor: Optional[str] = None,
        status: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Get portfolio orders. status: resting, canceled, executed."""
        params = {'limit': limit, 'cursor': cursor, 'status': status}
        params = {k: v for k, v in params.items() if v is not None}
        return self.get(self.portfolio_url + '/orders', params=params)

    def get_positions(
        self,
        limit: Optional[int] = None,
        cursor: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Get portfolio positions."""
        params = {'limit': limit, 'cursor': cursor}
        params = {k: v for k, v in params.items() if v is not None}
        return self.get(self.portfolio_url + '/positions', params=params)

    def create_order(
        self,
        ticker: str,
        action: str,
        side: str,
        count: int,
        order_type: str = "limit",
        yes_price: Optional[int] = None,
        no_price: Optional[int] = None,
        client_order_id: Optional[str] = None,
        time_in_force: Optional[str] = None,
        expiration_ts: Optional[int] = None,
    ) -> Dict[str, Any]:
        """Create an order.

        - action: buy|sell
        - side: yes|no
        - yes_price/no_price: cents (1–99)
        - time_in_force (REST): fill_or_kill, good_till_canceled, immediate_or_cancel
        - expiration_ts: Unix seconds when the order should expire (REST currently still appears as GTC when set)."""
        body = {
            "ticker": ticker,
            "action": action,
            "side": side,
            "count": count,
            "type": order_type,
        }
        if yes_price is not None:
            body["yes_price"] = yes_price
        if no_price is not None:
            body["no_price"] = no_price
        if client_order_id is None:
            client_order_id = str(uuid.uuid4())
        body["client_order_id"] = client_order_id
        if time_in_force:
            body["time_in_force"] = time_in_force
        if expiration_ts is not None:
            body["expiration_ts"] = expiration_ts
        return self.post(self.portfolio_url + '/orders', body)

    def cancel_order(self, order_id: str) -> Dict[str, Any]:
        """Cancel an order by id."""
        return self.delete(self.portfolio_url + '/orders/' + order_id)

    def batch_place_orders(
        self,
        orders: list,
    ) -> Dict[str, Any]:
        """Place up to MAX_BATCH_ORDERS orders sequentially with rate limiting. No recursion.
        Each item: {ticker, side, count, yes_price?, no_price?, action?}. Returns {placed: [], errors: []}."""
        results = {"placed": [], "errors": []}
        cap = min(len(orders), self.MAX_BATCH_ORDERS)
        for i in range(cap):
            o = orders[i]
            try:
                self.rate_limit()
                res = self.create_order(
                    ticker=o["ticker"],
                    action=o.get("action", "buy"),
                    side=o["side"],
                    count=int(o["count"]),
                    yes_price=o.get("yes_price"),
                    no_price=o.get("no_price"),
                    time_in_force=o.get("time_in_force"),
                    expiration_ts=int(o["expiration_ts"]) if isinstance(o.get("expiration_ts"), (int, float)) else None,
                )
                results["placed"].append(res)
            except Exception as e:
                results["errors"].append({"index": i, "ticker": o.get("ticker"), "error": str(e)})
        return results

class KalshiWebSocketClient(KalshiBaseClient):
    """Client for handling WebSocket connections to the Kalshi API."""
    def __init__(
        self,
        key_id: str,
        private_key: rsa.RSAPrivateKey,
        environment: str,
    ):
        super().__init__(key_id, private_key, environment)
        self.ws = None
        self.url_suffix = "/trade-api/ws/v2"
        self.message_id = 1  # Add counter for message IDs

    async def connect(self):
        """Establishes a WebSocket connection using authentication."""
        host = self.WS_BASE_URL + self.url_suffix
        auth_headers = self.request_headers("GET", self.url_suffix)
        async with websockets.connect(host, additional_headers=auth_headers) as websocket:
            self.ws = websocket
            await self.on_open()
            await self.handler()

    async def on_open(self):
        """Callback when WebSocket connection is opened."""
        print("WebSocket connection opened.")
        await self.subscribe_to_tickers()

    async def subscribe_to_tickers(self):
        """Subscribe to ticker updates for all markets."""
        subscription_message = {
            "id": self.message_id,
            "cmd": "subscribe",
            "params": {
                "channels": ["ticker"]
            }
        }
        await self.ws.send(json.dumps(subscription_message))
        self.message_id += 1

    async def handler(self):
        """Handle incoming messages."""
        try:
            async for message in self.ws:
                await self.on_message(message)
        except websockets.ConnectionClosed as e:
            await self.on_close(e.code, e.reason)
        except Exception as e:
            await self.on_error(e)

    async def on_message(self, message):
        """Callback for handling incoming messages."""
        print("Received message:", message)

    async def on_error(self, error):
        """Callback for handling errors."""
        print("WebSocket error:", error)

    async def on_close(self, close_status_code, close_msg):
        """Callback when WebSocket connection is closed."""
        print("WebSocket connection closed with code:", close_status_code, "and message:", close_msg)


def get_client(environment: str = "DEMO"):
    """Build HTTP client from env. Needs KALSHI_API_KEY (your Key ID from Kalshi). PEM path: KALSHI_PRIVATE_KEY_PATH or tocotoucan.pem in this folder."""
    key_id = os.getenv("KALSHI_API_KEY")
    if not key_id:
        raise ValueError(
            "Set KALSHI_API_KEY to your Kalshi API Key ID (from kalshi.com → Account → API keys). "
            "PEM: put tocotoucan.pem in betting_outs/kalshi or set KALSHI_PRIVATE_KEY_PATH."
        )
    key_path = _default_private_key_path()
    key = load_private_key(key_path)
    return KalshiHttpClient(key_id, key, environment)


if __name__ == "__main__":
    # Example: run HTTP client only (no WebSocket)
    client = get_client("DEMO")
    print(client.get_exchange_status())
    print(client.get_balance())