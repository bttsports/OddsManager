# Diagnostic: Why "Request aborted" was never shown

## What was intended
- When "Specific time" is selected and expiration is not valid → do NOT call the API and show toast: "Request aborted".
- No API call without valid specific time when that option is selected.

## What is in the code (submit handler flow)

1. **Lines 871–876**: `expirationType` and initial `expirationTs` are set.
   - If "Specific time" is selected but the datetime input is **empty**, the condition `kalshiOrderExpirationDatetime && kalshiOrderExpirationDatetime.value` is false, so we **do not** set `expirationTs`. It stays `null`.

2. **Lines 881–896**: Block runs only when `expirationType === "specific_time"`.
   - If datetime is missing/empty → we show **"Set expiration date/time for Specific time"** and **return** (no API call). ✓
   - If `ts` is NaN or ≤ 0 → we show **"Invalid expiration date/time"** and **return**. ✓
   - If `ts` is in the past → we show **"Expiration must be in the future"** and **return**. ✓
   - Otherwise we set `expirationTs = ts` and fall through.

3. **Lines 897–901**: "Request aborted" check:
   ```js
   expirationTsParam = expirationType !== "good_till_canceled" && expirationTs != null ? expirationTs : null;
   if (expirationType === "specific_time" && (expirationTsParam == null || typeof expirationTsParam !== "number" || isNaN(expirationTsParam))) {
     showToast("Cannot send order: expiration at specific time is required but not set. Request aborted.", "error");
     return;
   }
   ```

## Why the "Request aborted" toast is never shown

- When `expirationType === "specific_time"`, we **always** enter the block at 881–896.
- In that block we either:
  - **Return early** (empty, invalid, or past) with one of the three other toasts, or
  - **Set** `expirationTs = ts` (a valid number) and do not return.
- So we **never** leave that block with `expirationType === "specific_time"` and `expirationTs` still null or invalid.
- Therefore, when we reach line 898, we always have `expirationTsParam` = a valid number when "Specific time" is selected.
- So the condition on 899 is **always false** for "Specific time" → the "Request aborted" branch is **dead code** and never runs.

## Other issues

1. **Different messages**: When we abort for empty/invalid/past we show three different toasts. The promised single "Request aborted" message only exists in the unreachable branch.
2. **No single gate**: There is no one place that says: "If user chose specific time and we don’t have a valid future expiration, show ‘Request aborted’ and do not send."
3. **Possible race**: If the expiration dropdown is set to "Specific time" but the datetime **change** handler never ran (e.g. value never set), the input can be empty. We then hit the empty check and return with "Set expiration date/time...", not "Request aborted."

## Fix (implemented)

1. **Single path for "Specific time"**: As soon as `expirationType === "specific_time"`, we run one block that:
   - If datetime input is missing or empty → show **"Request aborted: expiration at specific time is required but not set."** and **return** (no API call).
   - If parsed timestamp is NaN or ≤ 0 → show **"Request aborted: expiration at specific time is required but not valid."** and **return**.
   - If timestamp is in the past → show **"Request aborted: expiration must be in the future."** and **return**.
   - Otherwise set `expirationTs = ts` and continue.

2. **Final gate** before building payload: if `expirationType === "specific_time"` and we do not have a valid numeric future `expirationTsParam`, show **"Request aborted: expiration at specific time is required but not valid or not set."** and **return**.

3. **Result**: We never call `invoke("kalshi_place_order", ...)` when "Specific time" is selected unless we have a valid future expiration. All abort cases use a "Request aborted" message.

## Timed limit orders (Good Till Date)

- REST [Create Order](https://docs.kalshi.com/api-reference/orders/create-order) documents `expiration_ts` but only lists `time_in_force` enum: fill_or_kill, good_till_canceled, immediate_or_cancel (no GTD).
- FIX [Order Entry](https://docs.kalshi.com/fix/order-entry) documents **TimeInForce=6** (Good Till Date) and **ExpireTime** (tag 126).
- For REST we now send **only `expiration_ts` in Unix seconds** for "Specific time", and **omit `time_in_force`** so the backend applies its default behavior (which currently still surfaces as GTC). "At event start" was removed because Kalshi does not expose a reliable scheduled start time for this use.
