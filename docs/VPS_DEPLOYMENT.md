# VPS Deployment for OddsManager Services

## Overview

This guide covers deploying OddsManager services (Kalshi API, future market-making bot) on a VPS so they run 24/7 and survive reboots.

**Project path on VPS:** `/home/your_user/projects/OddsManager` — replace `your_user` with your deploy username.

**Local setup:** Add `ODDSMANAGER_KALSHI_API=http://YOUR_VPS_IP:8766` to your project `.env` so the desktop app connects to the API on the VPS instead of localhost.

---

## 1. VPS provider quick comparison

| Provider | Cheapest tier | RAM | Notes |
|----------|---------------|-----|-------|
| **DigitalOcean** | ~$6/mo | 1GB | Simple UI, good docs |
| **Hetzner** | ~$3.50/mo | 2GB | Best value |
| **Vultr** | ~$2.50/mo | 512MB | Very cheap entry |
| **AWS Lightsail** | ~$3.50/mo | 512MB | Good if you prefer AWS |

**Recommendation:** Start with a 512MB–1GB instance. Python + Kalshi API + small web API is lightweight.

---

## 2. Initial VPS setup

### 2.1 Create droplet/instance (DigitalOcean)

1. Sign up at [digitalocean.com](https://digitalocean.com).
2. Create a new Droplet:
   - **Image:** Ubuntu 22.04 or 24.04 LTS
   - **Plan:** Basic, smallest (e.g. 1 vCPU, 1GB RAM)
   - **Region:** New York or another US East region (closer to Kalshi)
3. Add an SSH key for login.
4. Note the public IP.

### 2.2 First login

```bash
ssh root@YOUR_VPS_IP
```

### 2.3 Create deploy user

```bash
adduser your_user
usermod -aG sudo your_user
su - your_user
```

---

## 3. Install dependencies

```bash
sudo apt update && sudo apt upgrade -y
sudo apt install -y python3 python3-pip python3-venv git
```

---

## 4. Deploy the project

### Option A: Clone from Git

```bash
mkdir -p /home/your_user/projects
cd /home/your_user/projects
git clone https://github.com/YOUR_USER/OddsManager.git
cd OddsManager
```

### Option B: Copy from local machine

From your Windows machine (PowerShell or WSL):

```powershell
scp -r C:\Users\davpo\VSCodeProjects\OddsManager your_user@YOUR_VPS_IP:/home/your_user/projects/
```

### Set up Python environment

```bash
cd /home/your_user/projects/OddsManager
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
pip install flask requests python-dotenv cryptography  # if not in requirements
```

---

## 5. Environment variables (secrets)

Create `.env` in the project root:

```bash
nano /home/your_user/projects/OddsManager/.env
```

Add (adjust values):

```
KALSHI_API_KEY=your_api_key_id
KALSHI_PRIVATE_KEY_PATH=/home/your_user/projects/OddsManager/betting_outs/kalshi/tocotoucan.pem
KALSHI_API_PORT=8766
KALSHI_API_HOST=0.0.0.0
```

- **KALSHI_API_HOST=0.0.0.0** — Required on the VPS so the Flask server accepts connections from your desktop (not just localhost). Omit or use `127.0.0.1` for local-only.

Secure the file:

```bash
chmod 600 /home/your_user/projects/OddsManager/.env
```

---

## 6. Kalshi API: bind to 0.0.0.0 on VPS

The Kalshi API reads `KALSHI_API_HOST` from the environment:

| Value | Effect |
|-------|--------|
| `127.0.0.1` (default) | Listens only on localhost — safe for local dev |
| `0.0.0.0` | Listens on all interfaces — required so your desktop can connect remotely |

On the VPS, set `KALSHI_API_HOST=0.0.0.0` in `.env` (see §5). The systemd service inherits env vars from the environment; to pass them explicitly, add to the `[Service]` block:

```ini
Environment="KALSHI_API_HOST=0.0.0.0"
```

Or use an env file:

```ini
EnvironmentFile=/home/your_user/projects/OddsManager/.env
```

---

## 7. Firewall: allow port 8766

### Option A: Allow from your IP only (recommended)

Restrict port 8766 to your home/office IP to reduce exposure:

```bash
# Replace YOUR_HOME_IP with your public IP (check via https://whatismyip.com)
sudo ufw allow from YOUR_HOME_IP to any port 8766 proto tcp
sudo ufw allow 22/tcp   # SSH
sudo ufw enable
sudo ufw status
```

If your IP changes (e.g. dynamic ISP), you must run `ufw allow from NEW_IP ...` again.

### Option B: Allow from anywhere

```bash
sudo ufw allow 22/tcp
sudo ufw allow 8766/tcp
sudo ufw enable
```

**Security:** The Kalshi API has no built-in auth. Anyone who can reach port 8766 can use your API keys. Restricting by IP (Option A) is strongly recommended.

---

## 8. systemd service: Kalshi API

Create the service file:

```bash
sudo nano /etc/systemd/system/oddsmanager-kalshi-api.service
```

Paste (adjust `your_user`):

```ini
[Unit]
Description=OddsManager Kalshi API
After=network.target

[Service]
Type=simple
User=your_user
Group=your_user
WorkingDirectory=/home/your_user/projects/OddsManager
EnvironmentFile=/home/your_user/projects/OddsManager/.env
Environment="PATH=/home/your_user/projects/OddsManager/venv/bin"
ExecStart=/home/your_user/projects/OddsManager/venv/bin/python betting_outs/kalshi/kalshi_api.py
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```

`EnvironmentFile` loads `.env`, including `KALSHI_API_HOST=0.0.0.0`.

Enable and start:

```bash
sudo systemctl daemon-reload
sudo systemctl enable oddsmanager-kalshi-api
sudo systemctl start oddsmanager-kalshi-api
sudo systemctl status oddsmanager-kalshi-api
```

---

## 9. Bot control endpoints

The Kalshi API includes stub routes for the future market-making bot. The desktop app can call these to list strategies and restart stopped ones.

### GET /market-making/strategies

Returns all strategies and their status.

**Response (current stub):**
```json
{
  "strategies": []
}
```

**When implemented:** Each strategy will include `id`, `name`, `status` (e.g. `running`, `stopped`), `reason` (e.g. `max_shares_reached`), and related fields.

### POST /market-making/strategy/{id}/restart

Restarts a stopped strategy (e.g. after it hit max shares).

**Current behavior:** Returns `501 Not Implemented` until the bot exists.

**When implemented:** Resets strategy state and resumes placing/refilling orders.

---

## 10. Market Making: strategy script + installer (one bot per strategy)

For a persistent 24/7 bot per strategy, use **Generate strategy script** in the app. This produces:

- **Strategy script** (`.py`): saved to `market_making/` in the project root
- **Installer** (`.sh`): saved to `desktop/src-tauri/market_making_services/`

### File locations

| File | Local path | VPS path (after copy) |
|------|------------|------------------------|
| Strategy script | `market_making/mm_KXMAINE94_26.py` | `market_making/mm_KXMAINE94_26.py` |
| Installer | `desktop/src-tauri/market_making_services/install_mm_KXMAINE94_26.sh` | `desktop/src-tauri/market_making_services/install_mm_KXMAINE94_26.sh` |
| Config (optional) | `desktop/src-tauri/configs/` | `desktop/src-tauri/configs/` |

### Deploy and run

1. **In the app:** Load stakes, configure them, click **Generate strategy script**, and save. The `.py` goes to `market_making/` and the `.sh` is written to `desktop/src-tauri/market_making_services/`.

2. **Copy to the VPS** (adjust paths and event name):

   ```bash
   # From your local machine (PowerShell or bash)
   scp market_making/mm_KXMAINE94_26.py your_user@YOUR_VPS_IP:/home/your_user/projects/OddsManager/market_making/
   scp desktop/src-tauri/market_making_services/install_mm_KXMAINE94_26.sh your_user@YOUR_VPS_IP:/home/your_user/projects/OddsManager/desktop/src-tauri/market_making_services/
   ```

3. **On the VPS**, run the installer from `market_making_services/`:

   ```bash
   cd /home/your_user/projects/OddsManager/desktop/src-tauri/market_making_services
   chmod +x install_mm_KXMAINE94_26.sh
   ./install_mm_KXMAINE94_26.sh
   ```

   The installer creates the systemd service, enables it, and starts it. Defaults: `DEPLOY_USER=root`, `PYTHON=/home/your_user/venvs/myenv1/bin/python`. Override for project venv: `PYTHON=$PROJECT_ROOT/venv/bin/python ./install_mm_....sh`

4. **Multiple strategies:** Generate a separate script and installer for each event. Copy the `.py` to `market_making/` and the `.sh` to `market_making_services/` on the VPS, then run each installer from `market_making_services/`. Each creates its own systemd service (e.g. `oddsmanager-mm-kxmain94`, `oddsmanager-mm-txsenate`).

### Useful commands (per-strategy service)

| Command | Purpose |
|---------|---------|
| `sudo systemctl status oddsmanager-mm-kxmain94` | Check status |
| `sudo systemctl stop oddsmanager-mm-kxmain94` | Stop the bot |
| `sudo systemctl restart oddsmanager-mm-kxmain94` | Restart |
| `sudo journalctl -u oddsmanager-mm-kxmain94 -f` | Tail logs |

---

## 10a. Combined No Spread: strategy script + installer

The **Combined No Spread** bot offers No liquidity on all stakes when the combined best No ask across markets is below a threshold (e.g. 99¢). It cancels all orders when the condition fails. Polls every 5 seconds.

**In the app:** Kalshi tab → **Combined No Spread** → enter event ticker, Load stakes, select which stakes to include, set Max combined (¢) and Shares per market → **Generate strategy script**.

### File locations

| File | Local path | VPS path (after copy) |
|------|------------|------------------------|
| Strategy script | `market_making/combined_no_KXTXSENDPRIMARYMOV_26MAR03.py` | `market_making/combined_no_...py` |
| Installer | `desktop/src-tauri/market_making_services/install_combined_no_....sh` | same path on VPS |

### Deploy and run

Same flow as Market Making (section 10): copy the `.py` to `market_making/`, the `.sh` to `market_making_services/`, then run from `market_making_services/`:

```bash
cd /home/your_user/projects/OddsManager/desktop/src-tauri/market_making_services
chmod +x install_combined_no_KXTXSENDPRIMARYMOV_26MAR03.sh
./install_combined_no_KXTXSENDPRIMARYMOV_26MAR03.sh
```

Service name: `oddsmanager-combinedno-<event>` (e.g. `oddsmanager-combinedno-kxtxsendprimarymov26mar03`).

### Useful commands

| Command | Purpose |
|---------|---------|
| `sudo systemctl status oddsmanager-combinedno-kxtxsendprimarymov26mar03` | Check status |
| `sudo systemctl stop oddsmanager-combinedno-kxtxsendprimarymov26mar03` | Stop |
| `sudo journalctl -u oddsmanager-combinedno-kxtxsendprimarymov26mar03 -f` | Tail logs |

---

## 10b. Market Making: single config (legacy)

For one bot using `config.json` instead of generated scripts:

```bash
sudo nano /etc/systemd/system/oddsmanager-market-making.service
```

```ini
[Unit]
Description=OddsManager Market Making Bot
After=network.target oddsmanager-kalshi-api.service

[Service]
Type=simple
User=your_user
Group=your_user
WorkingDirectory=/home/your_user/projects/OddsManager
EnvironmentFile=/home/your_user/projects/OddsManager/.env
Environment="PATH=/home/your_user/projects/OddsManager/venv/bin"
ExecStart=/home/your_user/projects/OddsManager/venv/bin/python -m market_making.bot
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

**Config:** The bot reads `market_making/config.json`. In the app: configure stakes, click **Save config for VPS**, save the JSON. Copy to the VPS:

```bash
scp mm_Event_26_config.json your_user@YOUR_VPS_IP:/home/your_user/projects/OddsManager/market_making/config.json
```

Then:

```bash
sudo systemctl daemon-reload
sudo systemctl enable oddsmanager-market-making
sudo systemctl start oddsmanager-market-making
```

---

## 11. Deployment checklist

- [x] Create VPS (Ubuntu 22.04/24.04)
- [x] SSH in and create deploy user (`your_user`)
- [x] `apt update && apt upgrade`
- [x] Install Python 3, pip, venv, git
- [x] Deploy project to `/home/your_user/projects/OddsManager`
- [x] Create venv, install dependencies
- [x] Create `.env` with `KALSHI_API_KEY`, `KALSHI_PRIVATE_KEY_PATH`, `KALSHI_API_HOST=0.0.0.0`
- [x] Copy PEM file to VPS if needed
- [x] Create systemd service with `EnvironmentFile` for `.env`
- [x] `systemctl daemon-reload`, `enable`, `start`
- [x] Configure firewall (Option A: your IP only; Option B: open)
- [x] Add `ODDSMANAGER_KALSHI_API=http://YOUR_VPS_IP:8766` to your **local** project `.env`
- [ ] Verify: desktop app can reach the API and place orders

---

## 12. Useful commands

| Command | Purpose |
|---------|---------|
| `sudo systemctl status oddsmanager-kalshi-api` | Check Kalshi API status |
| `sudo systemctl restart oddsmanager-kalshi-api` | Restart Kalshi API |
| `sudo journalctl -u oddsmanager-kalshi-api -f` | Tail Kalshi API logs |
| `sudo systemctl status oddsmanager-mm-<event>` | Check market-making bot (e.g. `oddsmanager-mm-kxmain94`) |
| `sudo systemctl stop oddsmanager-mm-kxmain94` | Stop market-making bot |
| `sudo systemctl status oddsmanager-combinedno-<event>` | Check Combined No Spread bot |
| `sudo journalctl -u oddsmanager-mm-kxmain94 -f` | Tail market-making bot logs |

---

## 13. Security notes

- Use SSH keys, not passwords, for login.
- Keep `.env` and PEM files out of git; use `chmod 600` on secrets.
- Prefer firewall Option A (restrict port 8766 to your IP).
- Keep the system updated: `sudo apt update && sudo apt upgrade` periodically.
