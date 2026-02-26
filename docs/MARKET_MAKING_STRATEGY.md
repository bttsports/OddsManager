# Market Making Bot – Strategy & Design

## Overview

A Market Making sub-tab under the Kalshi tab lets users run a bot that keeps orders active on one or more markets. The bot can refill orders when filled, respect stop conditions, and post multiple sides. For persistence when the computer is off, the bot runs as a separate service on a VPS or always-on machine.

---

## 1. Two-part architecture: UI vs. bot engine

| Component | Role |
|-----------|------|
| **Desktop app (UI)** | Configure strategies, start/stop, monitor status |
| **Bot engine (separate process)** | Runs 24/7 on a VPS or Pi; executes orders, refills, enforces stops |

The desktop app configures and monitors; the bot engine executes and persists.

---

## 2. Bot engine: where and how it runs

| Option | Pros | Cons |
|--------|------|------|
| **VPS (AWS, DigitalOcean, Hetzner, etc.)** | Always on, low latency, remote management | Ongoing cost (~$3–10/mo) |
| **Raspberry Pi / always-on PC** | One-time cost, full control | Depends on power and network |
| **Serverless (Lambda, etc.)** | Pay-per-use | Poor fit for continuous order watching and refills |

**Recommendation:** Run the bot as a long-running Python daemon or Docker container on a VPS or Pi. Use systemd (Linux) or Windows Service to auto-start and restart on failure.

---

## 3. Communication between desktop and bot

| Approach | Pros | Cons |
|----------|------|------|
| **Config files + status files** | Simple, no network | Polling only, limited control |
| **REST API on the bot** | Clear contract, works remotely | Bot must expose an API |
| **WebSocket** | Real-time updates | More complex |

**Recommendation:** Bot exposes a small REST API (Flask/FastAPI). Desktop POSTs config and control; GETs status. Bot can run on LAN or VPS.

---

## 4. Strategy features and design

### Refill logic

- **Same price:** After a fill, place a new order at the same limit price.
- **Median (mid):** Use best bid/ask. Mid = (best_bid + best_ask) / 2; round to valid price (1–99¢).

Requires order book data: poll `/markets/{ticker}/orderbook` or use WebSocket if Kalshi provides one.

### Stop conditions

- **Max shares traded:** Sum filled size; stop when cap reached.
- **Max $ traded:** Track Σ(fill_price × fill_count); stop when cap reached.

Persist state (e.g. SQLite or JSON) so restart does not reset totals.

### Posting all sides

- **Binary (A vs B):** Use reciprocal logic. Post Yes on market A and No on market B (or both Yes on both markets).
- **N-way:** For each outcome market, post the chosen side (Yes/No) at the configured size.

Need to know which markets form an event (e.g. via `/market-reciprocal` or event-level API).

---

## 5. Data model

```
Strategy:
  id, name, enabled
  markets: [ticker1, ticker2, ...]  # or event_ticker for all outcomes
  sides: "yes" | "no" | "both" | "all"
  order_size: int (contracts per order)
  refill_mode: "same" | "median" | "offset"
  refill_offset_cents: int (optional, e.g. ±1)
  stop_max_shares: int | null
  stop_max_dollars: int | null  # cents
  check_interval_sec: int (e.g. 30)
  price_min, price_max: int | null  # optional bounds 1–99

State (per strategy):
  total_shares_filled, total_dollars_traded
  last_refill_ts, active_order_ids
```

---

## 6. Bot engine flow

1. Load config (file or API).
2. For each enabled strategy, resolve markets (ticker, event, or list).
3. Subscribe or poll order book and fills.
4. Loop:
   - If stop conditions met → disable strategy, notify.
   - If orders filled → update state; place refill orders per `refill_mode`.
   - If orders missing (cancelled, etc.) → place new ones.
   - Sleep `check_interval_sec`.
5. Persist state on changes and on shutdown.

---

## 7. Desktop UI: Market Making sub-tab

- **Event ticker browse:** Load all stakes for an event; expandable dropdown shows each stake.
- **Per-stake form:** For each stake, optionally configure:
  - **Shares, Side (Yes/No/Both), Yes (¢), No (¢)** – like the Place order form. Leave blank to skip.
  - **% reload** – when original shares are fully filled, repost this % of original (e.g. 75% of 1000 = 750).
  - **Repost price base:** `previous_fill` | `market_mean` (round down, e.g. 48.5→48) | `market_best_offer`.
  - **Cents off** – subtract from repost base to get new price.
  - **Max shares** – cap per stake; if repost would exceed total filled, skip repost and send alert.
- **Generate strategy script** – produces Python with embedded config; includes `send_alert()` and stub for order placement.
- **Alert webhook URL** – optional; bot POSTs `{"ticker","reason"}` when max shares hit. App can run a local listener to pick up alerts.

---

## 8. Security and rate limits

- Store Kalshi API keys in env vars or a secrets manager, not in config files.
- Respect Kalshi rate limits (existing client uses ~0.12s between calls).
- Expose bot API only on localhost or over HTTPS with auth if public.

---

## 9. Project structure (suggested)

```
market_making/
  bot.py           # Main daemon loop
  strategy.py      # Strategy config + state
  order_manager.py # Place/cancel, refill logic
  api.py           # Flask/FastAPI for config + control
  config.json      # Strategies (or DB)
  state.json       # Running totals
```

Reuse `betting_outs/kalshi/` client and existing Kalshi API integration.

---

## 10. Phased rollout

1. **Phase 1:** Bot runs locally, reads config from file, implements refill + stops. No desktop integration.
2. **Phase 2:** REST API for config and control; desktop Market Making tab to configure and start/stop.
3. **Phase 3:** Deploy bot to VPS for persistence; add monitoring/alerting.

---

## 11. Per-stake strategy – possible extensions

Things you might add as you iterate:

- **Cents off direction** – currently always subtract. You might want “add” for the opposite side (e.g. improve No by going higher).
- **Price bounds** – min/max cents (1–99) to avoid bad reposts.
- **Order expiration** – GTC vs. “fill by time” (e.g. expire at event close).
- **Cooldown after fast fill** – if filled “at once”, pause before reposting (historically-aware behavior).
- **Alert delivery** – besides webhook: in-app notification, email, or SMS.
