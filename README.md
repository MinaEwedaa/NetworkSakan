# 🌐 Karakery Monitor (مراقب شبكة كراكيري)

> **Zero-cost, per-device bandwidth and network monitor for shared student housing, dorms, and roommates.**  
> Monitor who is using the quota in real-time without purchasing any hardware or expensive managed routers.

---

## 📌 Problem & Motivation

In shared student housing or apartments ("Sakan"), internet quotas are often shared and limited (e.g., Telecom Egypt / WE, Vodafone, Orange). When the quota finishes in 10 days, nobody knows who consumed the gigabytes. 

Traditional solutions require:
- Buying expensive routers with per-IP bandwidth monitoring.
- Flashing custom firmware like OpenWrt / DD-WRT (often unsupported by ISP-locked VDSL routers).
- Purchasing dedicated mini-PCs or Raspberry Pis.

**NetworkSakan solves this with $0 cost:**  
By turning your Windows laptop into a transparent Wi-Fi gateway using Windows Mobile Hotspot, all traffic from connected roommates flows through your laptop. NetworkSakan sniffs and accounts for every byte per device in real-time and displays it on a dashboard.

---

## ✨ Features

- 📊 **Real-time Per-Device Bandwidth:** Live download & upload tracking per device MAC address.
- 📱 **Automatic Device Discovery:** Detects connected phones, laptops, and tablets via ARP sweep + Wi-Fi Direct interface monitoring.
- 🏷️ **Custom Device Nicknames:** Assign friendly names (e.g., *"Ahmed's iPhone"*, *"Omar's Laptop"*) directly from the UI.
- 🏢 **OUI Hardware Vendor Identification:** Identifies manufacturer (Apple, Samsung, Intel, Xiaomi, etc.) automatically.
- 📈 **Daily Usage & Trends:** Track daily historical consumption per device to split the internet bill fairly.
- 📥 **CSV Export:** Download bandwidth usage reports with one click for easy quota auditing.
- 🔔 **New Device Alerts:** Notifies you immediately when an unrecognized device connects.
- 🎨 **Modern Dark Web Dashboard:** Clean interface at `http://localhost:5000` with Chart.js visualization.

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
[Npcap Packet Sniffer (Scapy)]
            │
      [SQLite DB]
            │
[Flask REST API & Dashboard] (http://localhost:5000)
```

---

## 🚀 Quick Start

### Prerequisites
1. **Windows 10 or 11** with Wi-Fi adapter.
2. **Python 3.10+** installed and added to PATH.
3. **Npcap**: Download and install [Npcap](https://npcap.com/#download) with default settings (required for raw packet capture).

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

4. **Launch NetworkSakan:**
   - Double-click **`start.bat`** (or right-click → Run as Administrator),  
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
   Navigate to **[http://localhost:5000](http://localhost:5000)** in your browser.

---

## 🛠️ Tech Stack

- **Backend:** Python 3, Flask, Scapy, SQLite3, psutil, schedule
- **Capture Engine:** Npcap (WinPcap-compatible NDIS 6 driver)
- **Frontend:** Vanilla HTML5, CSS3 (Modern Dark Theme), Chart.js
- **Protocols:** Ethernet/IP packet inspection, ARP active scan, OUI API

---

## 🔒 Security & Privacy

- NetworkSakan operates **locally on your machine**.
- Packet payload data is **not inspected or stored**; only byte lengths, protocol headers, and source/destination MAC/IP addresses are counted for bandwidth aggregation.
- The SQLite database (`netmon.db`) remains entirely local and is excluded from git commits.

---

## 📄 License

MIT License. Free to use, modify, and distribute.
