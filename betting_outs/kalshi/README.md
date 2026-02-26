# Kalshi API integration

## Connecting your account

1. **API Key ID**  
   Create an API key at [kalshi.com](https://kalshi.com) → Account → API keys (or use the [demo environment](https://demo.kalshi.co) to test). You get a **Key ID** — set it as:
   ```bash
   set KALSHI_API_KEY=your_key_id_here
   ```
   (Use `export KALSHI_API_KEY=...` on macOS/Linux.)

2. **Private key (PEM)**  
   Your RSA private key file (e.g. `tocotoucan.pem`) must be available to the Kalshi bridge:
   - **Easiest:** Put `tocotoucan.pem` in this folder (`betting_outs/kalshi/`). It will be used automatically.
   - **Or** set the path explicitly:
     ```bash
     set KALSHI_PRIVATE_KEY_PATH=C:\full\path\to\tocotoucan.pem
     ```

3. **Run the app**  
   Start the desktop app, open the **Kalshi** tab, click **Start Kalshi API**, then choose **DEMO** or **PROD** and click **Refresh** to load balance and orders.

## Files

- `kalshi.py` — Kalshi HTTP/WebSocket client and auth.
- `kalshi_api.py` — Local Flask server (port 8766) used by the desktop app to call Kalshi.
- `tocotoucan.pem` — Your private key (keep secret; add to `.gitignore` if the repo is shared).
