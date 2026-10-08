# 🌐 Karakery Monitor (NetworkSakan - مراقب شبكة كراكيري)

> **Zero-cost, real-time per-device bandwidth and network monitor for shared apartments, student housing ("Sakan"), and dorms.**  
> Know exactly who is consuming your shared internet quota without purchasing expensive routers, managed switches, or Raspberry Pis.

---

## 📌 Problem & Motivation

In shared student housing or apartments in Egypt and across the region, internet quotas (Telecom Egypt / WE, Vodafone, Orange, Etisalat) are shared, expensive, and limited. When 140 GB or 250 GB finishes in 10 days, nobody knows who consumed the gigabytes.

Traditional network monitoring solutions require:
- Buying expensive routers with per-device bandwidth tracking and QoS.
- Flashing custom firmware like OpenWrt / DD-WRT (unsupported by most ISP-locked VDSL routers like HG630 / DG8045).
- Buying dedicated hardware like Raspberry Pis or managed switches.

**Karakery Monitor solves this for $0:**  
By turning your Windows laptop into a transparent Wi-Fi gateway using Windows Mobile Hotspot, all internet traffic from connected roommates flows directly through your laptop. Karakery Monitor sniffs raw packets on the hotspot interface in real-time, tallies every byte downloaded and uploaded per device, and serves a live web dashboard.

---

## ✨ Features

- 📊 **Real-time Per-Device Bandwidth:** Live download & upload tracking per device MAC address.
- 🟢 **Live Auto-Refresh & Disconnect Handling:**
  - Auto-refreshes every 2 seconds.
  - **Connected Only Tab:** Active devices only; automatically drops disconnected devices in real time.
  - **All Devices Tab:** Full history with "last active" relative timers (`active now`, `15s ago`, `35m ago`).
  - **Delete / Purge Button (🗑️):** Clean up old or guest devices from history.
- ⚡ **Dual Detection Engine:**
  - **Packet Sniffing Auto-Registration:** Instantly registers any device sending/receiving traffic through the hotspot, even before an ARP scan finishes.
  - **Full ARP & Neighbor Discovery:** Supports both `dynamic` and `static`/`permanent` leases assigned by Windows ICS / Mobile Hotspot.
- 🏷️ **Custom Device Nicknames:** Assign friendly labels (e.g., *"Ahmed's iPhone"*, *"Omar's Laptop"*) directly from the UI.
- 🏢 **OUI Hardware Vendor Identification:** Identifies manufacturer (Apple, Samsung, Intel, Xiaomi, etc.) automatically.
- 🚫 **Multicast Filtering:** Automatically filters out IPv4 (`01:...`) and IPv6 (`33:33:...`) multicast traffic to eliminate ghost/phantom entries.
- 📈 **Daily Usage & Trends:** Track daily historical consumption per device to split the internet bill fairly.
- 📱 **Mobile-Friendly UI:** Open the dashboard directly on your phone or tablet at `http://192.168.137.1:5000`.
- 📥 **CSV Export:** Download bandwidth usage reports with one click for easy quota auditing.
- 🔔 **New Device Alerts:** Notifies you immediately when an unrecognized device connects.

---

## 🏗️ Architecture

```
Internet (ISP Router / Wi-Fi)
            │
      [Laptop Wi-Fi]
            │
   [Windows Mobile Hotspot]  ─── Subnet: 192.168.137.x
            │
    ┌───────┴───────┐
    │               │
Roommate 1      Roommate 2 ...
 (Phone)         (Laptop)
    │               │
    └───────┬───────┘
            ▼
[Npcap Packet Sniffer (Scapy)]  ─── Captures raw Ethernet/IP frames
            │
      [SQLite DB]               ─── Aggregates realtime & daily totals
            │
[Flask REST API & Dashboard]    ─── Serves UI at http://localhost:5000
```

---

## 🚀 Quick Start

### Prerequisites
1. **Windows 10 or 11** with a Wi-Fi adapter.
2. **Python 3.10+** installed and added to PATH.
3. **Npcap**: Download and install [Npcap](https://npcap.com/#download) with default settings (required for Windows packet sniffing).

---

### Installation

1. **Clone the repository:**
   ```bash
   git clone https://github.com/MinaEwedaa/NetworkSakan.git
   cd NetworkSakan
   ```

2. **Install dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

3. **Turn On Windows Mobile Hotspot:**
   - Go to **Windows Settings** → **Network & Internet** → **Mobile Hotspot**.
   - Turn it **ON** (set "Share my internet connection from: Wi-Fi").
   - Share network name & password with your roommates.

4. **Launch Karakery Monitor:**
   - Double-click **`start.bat`** (it will automatically request Administrator privileges needed for raw packet capture).  
   *OR* run manually in two terminals:

   **Terminal 1 (Administrator for packet capture):**
   ```powershell
   python monitor.py
   ```

   **Terminal 2 (Dashboard):**
   ```powershell
   python dashboard.py
   ```

5. **Open Dashboard:**  
   - On your laptop: **[http://localhost:5000](http://localhost:5000)**
   - On any phone connected to the hotspot: **`http://192.168.137.1:5000`**

---

## 🌐 Remote Access (Outside the House)

Since Karakery Monitor sniffs physical network traffic passing through your laptop adapter, it runs locally on your machine (it cannot run on serverless cloud hosts like Vercel).

If you want a free, secure public link to check the dashboard from outside the house:

1. Install Cloudflare Tunnel:
   ```powershell
   winget install Cloudflare.cloudflared
   ```
2. Start tunnel:
   ```powershell
   cloudflared tunnel --url http://localhost:5000
   ```
3. Open the generated `https://....trycloudflare.com` URL anywhere on your phone!

---

## 🛠️ Tech Stack

- **Backend:** Python 3, Flask, Scapy, SQLite3, psutil, schedule
- **Capture Engine:** Npcap (NDIS 6 packet capture driver)
- **Frontend:** Vanilla HTML5, CSS3 (Modern Dark Theme), Chart.js
- **Protocols:** Ethernet/IP packet inspection, ARP active sweep, Windows Neighbor Cache, OUI API

---

## 🔒 Security & Privacy

- Karakery Monitor operates **100% locally on your machine**.
- Packet contents/payloads are **never inspected, parsed, or stored**; only byte lengths, protocol headers, and source/destination MAC/IP addresses are tallied for quota measurement.
- The SQLite database (`netmon.db`) remains entirely local and is excluded from git commits.

---

## 📄 License

MIT License. Free to use, modify, and distribute.
