# Tactical RMM — Advanced Remote Monitoring & Management System

Tactical RMM is a high-performance Remote Monitoring & Management (RMM) platform featuring a real-time Command Hub, automated multi-format agent generation, and zero-configuration remote telemetry for Windows endpoints.

---

## 🌟 Key Features

* **Real-Time Fleet Dashboard**: Live telemetry, online/offline status, CPU/RAM/Disk utilization, and system hardware metrics over WebSockets.
* **Multi-Format Agent Deployment Engine**:
  * **Standalone Executable (.exe)**: One-click native Windows binary package.
  * **Batch Installer (.bat)**: Lightweight script installer with automatic fallback mirrors.
  * **Silent VBScript Installer (.vbs)**: Native Windows Script Host deployment with auto-dismissing visual status popups and `/silent` CLI support.
  * **PowerShell 1-Click Deployment**: One-liner command for instant remote terminal provisioning.
  * **Full Offline Zip Package (.zip)**: Complete portable bundle for air-gapped or restricted networks.
* **All Agents Package Repository**: Browse, search, filter, and redownload any previously generated agent packages across all deployment formats.
* **Remote Shell & Terminal**: Interactive command execution streamed in real-time.
* **Remote Desktop & Screen Viewer**: Live screen streaming and viewer for connected endpoints.
* **Over-the-Air (OTA) Live Updates**: In-place agent code updates without requiring manual re-installation.
* **Security & Access Control**: Secure administrator authentication, session locking, and CORS protection.

---

## 🏗️ Architecture

```
TRMM/
├── master_hub/                  # Master Server (FastAPI + WebSockets)
│   ├── app.py                   # REST API routes and WebSocket handlers
│   ├── generator.py             # Agent compiler and packager (EXE, BAT, VBS, ZIP)
│   ├── registry.py              # Agent registry and package lifecycle management
│   ├── auth.py                  # Administrator authentication & session tokens
│   ├── agent_manager.py         # In-memory fleet state & WebSocket broker
│   ├── ota_manager.py           # Over-the-air code manifest & distribution
│   ├── static/                  # Responsive glassmorphism dashboard UI
│   │   ├── index.html           # Main command console markup
│   │   ├── app.js               # Reactive dashboard controller
│   │   ├── style.css            # Dark mode glassmorphism styles
│   │   └── login.html           # Authentication portal
│   └── payloads/                # Agent bootstrapper binaries & fixtures
├── agent_service/               # Endpoint Agent
│   ├── service.py               # Core background telemetry & task runner
│   ├── client.py                # WebSocket connection manager with backoff
│   └── platform/                # Windows API bindings (system metrics, screen capture)
├── run_master.py                # Hub entrypoint and server launcher
└── diagnostics/                 # System verification tests & acceptance suites
```

---

## 🚀 Quick Start (Local Development)

### 1. Prerequisites
* Python 3.10+ (Python 3.11, 3.12, 3.13, 3.14 supported)
* Windows (for agent builds and Windows API bindings)

### 2. Install Dependencies
```powershell
pip install -r requirements.txt
```

### 3. Launch Master Hub
```powershell
python run_master.py
```
Open **[http://localhost:8000](http://localhost:8000)** in your browser.

---

## 📦 Generating & Deploying Agents

1. Log in to the Command Console.
2. Click **"+ New Agent"** in the top navigation bar.
3. Configure the agent parameters:
   * **Endpoint Tag**: e.g., `Finance-PC`, `Workstation-01`.
   * **Server Connection URL**: Set your domain or IP (e.g., `wss://rmm.yourdomain.com`).
   * **Architecture**: 64-bit (x64) or 32-bit (x86).
   * **Options**: Auto-start on boot, Stealth/Hidden mode.
4. Click **"Build & Generate Package"**.
5. Choose your deployment method:
   * **Standalone Exe (.exe)**: Direct native setup.
   * **Batch Installer (.bat)**: Fast enterprise script deployment.
   * **VBScript Silent (.vbs)**: Windows Script Host installer with desktop status toasts.
   * **1-Click PowerShell**: Copy and run in an administrative PowerShell terminal.
   * **Offline ZIP**: Complete zip archive containing all agent dependencies.

---

## 🌐 Production Deployment Guide

To deploy Tactical RMM live on a cloud server or VPS:

### 1. Host Requirements
* **OS**: Ubuntu 22.04 LTS, Debian 12, or Windows Server 2022.
* **Ports**: `80`, `443` (HTTP/HTTPS) and optionally `8000` (Hub internal).
* **Domain**: A registered domain or subdomain (e.g., `rmm.example.com`).

### 2. Reverse Proxy Setup (Nginx + Let's Encrypt SSL)
Configure Nginx with WebSocket support:

```nginx
server {
    server_name rmm.example.com;

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_read_timeout 86400;
    }

    listen 443 ssl;
    ssl_certificate /etc/letsencrypt/live/rmm.example.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/rmm.example.com/privkey.pem;
}
```

### 3. Running as a Background Service (Linux Systemd)
Create `/etc/systemd/system/trmm.service`:
```ini
[Unit]
Description=Tactical RMM Master Hub
After=network.target

[Service]
User=root
WorkingDirectory=/opt/TRMM
ExecStart=/usr/bin/python3 run_master.py --host 0.0.0.0 --port 8000 --no-reload
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```

Enable and start:
```bash
sudo systemctl daemon-reload
sudo systemctl enable --now trmm
```

---

## 🛡️ License & Compliance
Proprietary software for authorized remote management and IT administration. Unauthorized deployment or distribution on unmanaged endpoints is strictly prohibited.
