# VPS Deployment for OddsManager Services

## Overview

This guide covers deploying OddsManager services (e.g. Kalshi API, market-making bot) on a VPS so they run 24/7 and survive reboots.

---

## 1. VPS provider quick comparison

| Provider | Cheapest tier | RAM | Notes |
|----------|---------------|-----|-------|
| **Hetzner** | ~$3.50/mo | 2GB | Best value |
| **DigitalOcean** | ~$6/mo | 1GB | Simple UI, good docs |
| **Vultr** | ~$2.50/mo | 512MB | Very cheap entry |
| **AWS Lightsail** | ~$3.50/mo | 512MB | Good if you prefer AWS |

**Recommendation:** Start with a 512MB–1GB instance. Python + Kalshi API + small web API is lightweight.

---

## 2. Initial VPS setup

### 2.1 Create droplet/instance

1. Sign up with your chosen provider (DigitalOcean, Hetzner, etc.).
2. Create a new droplet/instance:
   - **OS:** Ubuntu 22.04 or 24.04 LTS
   - **Size:** Smallest or next-smallest (e.g. 1 vCPU, 512MB–1GB RAM)
   - **Region:** Pick one close to Kalshi (likely US East if Kalshi is there)
3. Add an SSH key for login.
4. Note the public IP.

### 2.2 First login

```bash
ssh root@YOUR_VPS_IP
```

### 2.3 Create a non-root user (recommended)

```bash
adduser oddsmanager
usermod -aG sudo oddsmanager
su - oddsmanager
```

---

## 3. Install dependencies

```bash
# Update system
sudo apt update && sudo apt upgrade -y

# Python 3 + pip
sudo apt install -y python3 python3-pip python3-venv

# Git (to clone repo, or use scp/rsync to deploy)
sudo apt install -y git
```

---

## 4. Deploy the project

### Option A: Clone from Git

```bash
cd /home/oddsmanager
git clone https://github.com/YOUR_USER/OddsManager.git
cd OddsManager
```

### Option B: Copy from local machine

From your Windows machine (PowerShell or WSL):

```powershell
scp -r C:\Users\davpo\VSCodeProjects\OddsManager oddsmanager@YOUR_VPS_IP:/home/oddsmanager/
```

### Set up Python environment

```bash
cd /home/oddsmanager/OddsManager
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
pip install flask requests python-dotenv cryptography  # if not in requirements
```

---

## 5. Environment variables (secrets)

Create a `.env` file in the project root:

```bash
nano /home/oddsmanager/OddsManager/.env
```

Add (adjust paths and values):

```
KALSHI_API_KEY=your_api_key_id
KALSHI_PRIVATE_KEY_PATH=/home/oddsmanager/OddsManager/betting_outs/kalshi/tocotoucan.pem
KALSHI_API_PORT=8766
```

Secure the file:

```bash
chmod 600 /home/oddsmanager/OddsManager/.env
```

---

## 6. systemd service file: Kalshi API

Create a service so the Kalshi API starts on boot and restarts on failure.

```bash
sudo nano /etc/systemd/system/oddsmanager-kalshi-api.service
```

Paste:

```ini
[Unit]
Description=OddsManager Kalshi API
After=network.target

[Service]
Type=simple
User=oddsmanager
Group=oddsmanager
WorkingDirectory=/home/oddsmanager/OddsManager
Environment="PATH=/home/oddsmanager/OddsManager/venv/bin"
ExecStart=/home/oddsmanager/OddsManager/venv/bin/python betting_outs/kalshi/kalshi_api.py
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```

**Note:** If `kalshi_api` is run differently (e.g. `python betting_outs/kalshi/kalshi_api.py`), adjust `ExecStart` accordingly.

Enable and start:

```bash
sudo systemctl daemon-reload
sudo systemctl enable oddsmanager-kalshi-api
sudo systemctl start oddsmanager-kalshi-api
sudo systemctl status oddsmanager-kalshi-api
```

---

## 7. systemd service file: Market Making bot (future)

When the bot exists, use a similar service:

```bash
sudo nano /etc/systemd/system/oddsmanager-market-making.service
```

```ini
[Unit]
Description=OddsManager Market Making Bot
After=network.target oddsmanager-kalshi-api.service

[Service]
Type=simple
User=oddsmanager
Group=oddsmanager
WorkingDirectory=/home/oddsmanager/OddsManager
Environment="PATH=/home/oddsmanager/OddsManager/venv/bin"
ExecStart=/home/oddsmanager/OddsManager/venv/bin/python -m market_making.bot
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

---

## 8. Firewall (optional but recommended)

```bash
sudo ufw allow 22/tcp    # SSH
sudo ufw allow 8766/tcp  # Kalshi API (if you want desktop to reach it)
sudo ufw enable
```

---

## 9. Deployment checklist

- [ ] Create VPS (Ubuntu 22.04/24.04)
- [ ] SSH in and create non-root user
- [ ] `apt update && apt upgrade`
- [ ] Install Python 3, pip, venv, git
- [ ] Deploy project (git clone or scp)
- [ ] Create venv, install dependencies
- [ ] Create `.env` with KALSHI_API_KEY, KALSHI_PRIVATE_KEY_PATH
- [ ] Copy PEM file to VPS if needed
- [ ] Create systemd service file
- [ ] `systemctl daemon-reload`, `enable`, `start`
- [ ] `systemctl status` to verify running
- [ ] (Optional) Configure firewall
- [ ] Update desktop app to use `http://YOUR_VPS_IP:8766` instead of localhost if needed

---

## 10. Useful commands

| Command | Purpose |
|---------|---------|
| `sudo systemctl status oddsmanager-kalshi-api` | Check status |
| `sudo systemctl restart oddsmanager-kalshi-api` | Restart service |
| `sudo journalctl -u oddsmanager-kalshi-api -f` | Tail logs |
| `sudo journalctl -u oddsmanager-kalshi-api -n 100` | Last 100 log lines |

---

## 11. Security notes

- Use SSH keys, not passwords, for login.
- Keep `.env` and PEM files out of git and with restrictive permissions (`chmod 600`).
- If the Kalshi API is reachable from the internet, consider adding auth or restricting by IP.
- Keep the system updated: `sudo apt update && sudo apt upgrade` periodically.
