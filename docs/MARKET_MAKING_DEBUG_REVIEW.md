# Market Making Interface – Debug & Review

## Summary of Findings and Fixes

### 1. **max_shares not working – FIXED (fill_count bug)**

**Root cause:** The bot was using the wrong Kalshi API fields to get the filled quantity.

- **Before:** `order.get("count")` or `order.get("remaining_count")` – for executed orders, `remaining_count` is 0, so fills were undercounted.
- **After:** Uses `fill_count` (primary) and `initial_count` (fallback) per Kalshi’s Order schema.

With undercounted fills, `total_filled` stayed low and never reached `max_shares`, so the bot kept reposting.

### 2. **Poll reliability – IMPROVED**

- Poll now filters by `event_ticker` so we only fetch executed orders for this event.
- Limit increased from 100 to 200.
- Prevents missing fills when there are many executed orders across events.

### 3. **repost_size when near max_shares – IMPROVED**

**Before:** If `repost_size > remaining`, the bot paused entirely.

**After:** `repost_size` is capped to `remaining`, so it places one last smaller order up to `max_shares` instead of stopping early.

---

## Script Generation Flow

1. **UI** (Market Making tab): Load stakes → configure shares, side, prices, pct_reload, repost_base, cents_off, max_shares → Generate strategy script.
2. **collectMmStakeConfig()** (app.js): Reads form fields; includes only stakes with `shares > 0`.
3. **save_mm_strategy_script** (lib.rs): Serializes config to JSON, embeds in Python script, writes:
   - `market_making/mm_{event}.py` – strategy script
   - `desktop/src-tauri/market_making_services/install_mm_{event}.sh` – systemd installer

### Config fields passed through

| Field        | Description                        | Example   |
|-------------|------------------------------------|-----------|
| shares      | Order size                         | 1200      |
| side        | yes / no / both                    | no        |
| yes_price   | Initial Yes price (¢), null = skip | null      |
| no_price    | Initial No price (¢), null = skip  | 86        |
| pct_reload  | Repost size as % of original       | 75        |
| repost_base | previous_fill / market_mean / market_best_offer | market_best_offer |
| cents_off   | Cents below base for repost        | 1         |
| max_shares  | Stop after this many filled        | 2500      |

---

## Your Script: mm_KXTXSENDPRIMARYMOV_26MAR03.py

### Stakes with initial orders (6)

Only stakes with `no_price` set get initial orders:

- JTAL-P10: 1500 shares @ 86¢ No, max_shares 3000  
- JTAL-P1: 1200 @ 88¢ No, max 2500  
- JCRO-P7: 1200 @ 95¢ No, max 2500  
- JCRO-P54: 1200 @ 94¢ No, max 2500  
- JCRO-P4: 1200 @ 90¢ No, max 2500  
- JCRO-P1: 1200 @ 87¢ No, max 2500  

### Stakes without initial orders (5)

These have `yes_price` and `no_price` both null; they never place:

- JTAL-P7, JTAL-P59, JTAL-P4, JTAL-P16, JTAL-P13  

### Repost behavior

- **repost_base:** market_best_offer  
- **cents_off:** 1  
- Repost price: best No ask − 1¢ (for side No)  
- **pct_reload:** 75% → e.g. 1200 → 900  
- **max_shares:** hard cap; once reached, no more reposts.

---

## .sh Installer (install_mm_KXTXSENDPRIMARYMOV_26MAR03.sh)

- Sets `KALSHI_ENV=PROD`.
- Runs `mm_KXTXSENDPRIMARYMOV_26MAR03.py` via systemd.
- No runtime params; config is embedded in the script.
- Poll interval: 30s (from config).

Behavior of repost and max_shares comes from the Python bot, not the .sh file.

---

## Kalshi API rules (relevant to MM)

| Rule                 | Notes                                                    |
|----------------------|----------------------------------------------------------|
| client_order_id      | Must be unique among open orders; 409 if duplicate       |
| fill_count           | Correct field for filled size on executed orders         |
| initial_count        | Original order size                                      |
| get_orders           | Supports event_ticker, ticker for filtering              |
| Historical cutoff    | Old executed orders may require historical endpoint      |

---

## Verification checklist

- [x] `fill_count` used for executed orders  
- [x] Poll filters by `event_ticker`  
- [x] `repost_size` capped by remaining when near `max_shares`  
- [ ] Confirm Kalshi response uses `fill_count` (and not different keys) in production
