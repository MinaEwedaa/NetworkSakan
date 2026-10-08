"""
monitor.py — Network Monitor Daemon
Captures ALL packets on the Windows Mobile Hotspot interface.
Counts bytes per device MAC in real-time.
Stores everything in SQLite. Dashboard at http://localhost:5000
Run as Administrator (required for packet capture).
"""

import sqlite3, threading, time, re, socket, os, collections, subprocess
from datetime import datetime, date
import requests, psutil, schedule

# ── Config ────────────────────────────────────────────────────────────────────
HOTSPOT_SUBNET = "192.168.137"   # Windows Mobile Hotspot default
DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "netmon.db")
SCAN_INTERVAL  = 30

# ── Per-device byte counters (RAM, flushed to DB every 10s) ──────────────────
_counters     = collections.defaultdict(lambda: {"bytes_in":0,"bytes_out":0,
                                                  "pkts_in":0,"pkts_out":0,"ip":""})
_counter_lock = threading.Lock()
HOTSPOT_MAC   = ""

# ── Database ──────────────────────────────────────────────────────────────────
def init_db():
    conn = sqlite3.connect(DB_PATH)
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS devices (
            mac        TEXT PRIMARY KEY,
            ip         TEXT,
            hostname   TEXT,
            vendor     TEXT,
            label      TEXT,
            first_seen TEXT,
            last_seen  TEXT,
            is_online  INTEGER DEFAULT 0
        );
        CREATE TABLE IF NOT EXISTS presence (
            id       INTEGER PRIMARY KEY AUTOINCREMENT,
            mac      TEXT, ip TEXT, status TEXT, seen_at TEXT
        );
        CREATE TABLE IF NOT EXISTS bandwidth_realtime (
            id        INTEGER PRIMARY KEY AUTOINCREMENT,
            ts        TEXT, mac TEXT, ip TEXT,
            bytes_in  INTEGER DEFAULT 0, bytes_out INTEGER DEFAULT 0,
            pkts_in   INTEGER DEFAULT 0, pkts_out  INTEGER DEFAULT 0
        );
        CREATE TABLE IF NOT EXISTS bandwidth_daily (
            date      TEXT, mac TEXT,
            bytes_in  INTEGER DEFAULT 0, bytes_out INTEGER DEFAULT 0,
            PRIMARY KEY (date, mac)
        );
        CREATE TABLE IF NOT EXISTS bandwidth_host (
            id        INTEGER PRIMARY KEY AUTOINCREMENT,
            ts        TEXT, mbps_up REAL, mbps_down REAL,
            bytes_sent INTEGER, bytes_recv INTEGER
        );
        CREATE TABLE IF NOT EXISTS alerts (
            id      INTEGER PRIMARY KEY AUTOINCREMENT,
            ts      TEXT, mac TEXT, message TEXT, seen INTEGER DEFAULT 0
        );
        CREATE INDEX IF NOT EXISTS idx_bw_rt_mac  ON bandwidth_realtime(mac);
        CREATE INDEX IF NOT EXISTS idx_bw_rt_ts   ON bandwidth_realtime(ts);
        CREATE INDEX IF NOT EXISTS idx_bw_day_mac ON bandwidth_daily(mac);
    """)
    conn.commit(); conn.close()
    print(f"[DB] Ready at {DB_PATH}")

def db():
    c = sqlite3.connect(DB_PATH)
    c.row_factory = sqlite3.Row
    return c

def now():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")

# ── Find hotspot interface ────────────────────────────────────────────────────
def find_hotspot_iface():
    from scapy.arch.windows import get_windows_if_list
    for iface in get_windows_if_list():
        for ip in iface.get("ips", []):
            if ip.startswith(HOTSPOT_SUBNET):
                print(f"[NET] Hotspot iface: {iface['name']}  ip={ip}")
                return iface["name"], iface.get("mac","").upper()
    return None, None

# ── Packet handler ────────────────────────────────────────────────────────────
def packet_handler(pkt):
    from scapy.all import Ether, IP
    if not pkt.haslayer(Ether):
        return
    src = pkt[Ether].src.upper()
    dst = pkt[Ether].dst.upper()
    ln  = len(pkt)
    # Ignore broadcast, multicast (IPv4 & IPv6), and loopback
    if dst == "FF:FF:FF:FF:FF:FF" or dst.startswith("01:") or dst.startswith("33:33"):
        return
    if src == "FF:FF:FF:FF:FF:FF" or src.startswith("01:") or src.startswith("33:33"):
        return
    with _counter_lock:
        if src != HOTSPOT_MAC:
            _counters[src]["bytes_out"] += ln
            _counters[src]["pkts_out"]  += 1
            if pkt.haslayer(IP) and pkt[IP].src.startswith(HOTSPOT_SUBNET):
                _counters[src]["ip"] = pkt[IP].src
        if dst != HOTSPOT_MAC:
            _counters[dst]["bytes_in"] += ln
            _counters[dst]["pkts_in"]  += 1
            if pkt.haslayer(IP) and pkt[IP].dst.startswith(HOTSPOT_SUBNET):
                _counters[dst]["ip"] = pkt[IP].dst

def start_capture(iface):
    from scapy.all import sniff
    print(f"[CAPTURE] Sniffing on: {iface}")
    sniff(iface=iface, prn=packet_handler, store=False)

# ── Flush counters → DB ───────────────────────────────────────────────────────
def flush_counters():
    with _counter_lock:
        snap = {mac: dict(v) for mac, v in _counters.items()}
        _counters.clear()
    if not snap:
        return
    conn  = db()
    ts    = now()
    today = date.today().isoformat()
    for mac, d in snap.items():
        if mac == "FF:FF:FF:FF:FF:FF" or mac.startswith("01:") or mac.startswith("33:33"):
            continue
        conn.execute("""
            INSERT INTO bandwidth_realtime (ts,mac,ip,bytes_in,bytes_out,pkts_in,pkts_out)
            VALUES (?,?,?,?,?,?,?)
        """, (ts, mac, d["ip"], d["bytes_in"], d["bytes_out"], d["pkts_in"], d["pkts_out"]))
        conn.execute("""
            INSERT INTO bandwidth_daily (date,mac,bytes_in,bytes_out) VALUES (?,?,?,?)
            ON CONFLICT(date,mac) DO UPDATE SET
                bytes_in  = bytes_in  + excluded.bytes_in,
                bytes_out = bytes_out + excluded.bytes_out
        """, (today, mac, d["bytes_in"], d["bytes_out"]))

        # Ensure device exists in devices table even if ARP sweep hasn't completed
        row = conn.execute("SELECT mac FROM devices WHERE mac=?", (mac,)).fetchone()
        if row is None:
            vendor = lookup_vendor(mac)
            conn.execute("""
                INSERT INTO devices (mac,ip,hostname,vendor,first_seen,last_seen,is_online)
                VALUES (?,?,?,?,?,?,1)
            """, (mac, d["ip"], None, vendor, ts, ts))
            print(f"[!] NEW DEVICE VIA PACKET: {mac} ({d['ip']}) — {vendor}")
        else:
            if d["ip"]:
                conn.execute("UPDATE devices SET last_seen=?,ip=?,is_online=1 WHERE mac=?",
                    (ts, d["ip"], mac))
            else:
                conn.execute("UPDATE devices SET last_seen=?,is_online=1 WHERE mac=?",
                    (ts, mac))
    conn.commit(); conn.close()

# ── ARP scan ──────────────────────────────────────────────────────────────────
OUI_CACHE = {}
def lookup_vendor(mac):
    oui = mac[:8]
    if oui in OUI_CACHE: return OUI_CACHE[oui]
    try:
        r = requests.get(f"https://api.macvendors.com/{oui}", timeout=5)
        if r.status_code == 200:
            OUI_CACHE[oui] = r.text.strip(); return OUI_CACHE[oui]
    except: pass
    return "Unknown"

def resolve_hostname(ip):
    try: return socket.gethostbyaddr(ip)[0]
    except: return None

def arp_scan():
    print(f"[SCAN] Sweeping {HOTSPOT_SUBNET}.1-254 ...")
    threads = []
    for i in range(1, 255):
        t = threading.Thread(
            target=lambda ip=f"{HOTSPOT_SUBNET}.{i}": subprocess.run(
                ["ping","-n","1","-w","200",ip], capture_output=True, timeout=1),
            daemon=True)
        threads.append(t); t.start()
    for t in threads: t.join(timeout=1.5)

    result  = subprocess.run(["arp","-a"], capture_output=True, text=True)
    # Match both dynamic and static/permanent ARP entries
    pattern = re.compile(r'(192\.168\.137\.\d+)\s+([\da-f-]+)\s+(?:dynamic|static|permanent)', re.I)
    found   = []
    for m in pattern.finditer(result.stdout):
        ip  = m.group(1)
        mac = m.group(2).replace("-",":").upper()
        if mac.startswith("FF") or mac.startswith("01") or mac.startswith("33:33"):
            continue
        if ip.endswith(".1") or ip.endswith(".255"):
            continue
        found.append((ip, mac))

    print(f"[SCAN] {len(found)} devices on hotspot")
    upsert_devices(found)

def upsert_devices(found):
    conn = db(); ts = now()
    # Mark devices offline only if not seen recently (> 3 minutes)
    conn.execute("""
        UPDATE devices SET is_online=0
        WHERE last_seen < datetime('now', '-3 minutes')
    """)
    for ip, mac in found:
        hostname = resolve_hostname(ip)
        row = conn.execute("SELECT mac FROM devices WHERE mac=?", (mac,)).fetchone()
        if row is None:
            vendor = lookup_vendor(mac)
            conn.execute("""
                INSERT INTO devices (mac,ip,hostname,vendor,first_seen,last_seen,is_online)
                VALUES (?,?,?,?,?,?,1)
            """, (mac, ip, hostname, vendor, ts, ts))
            conn.execute("INSERT INTO alerts (ts,mac,message) VALUES (?,?,?)",
                (ts, mac, f"New device: {hostname or mac} ({ip}) — {vendor}"))
            print(f"[!] NEW DEVICE: {mac}  {ip}  {hostname}  {vendor}")
        else:
            conn.execute("""UPDATE devices SET ip=?,hostname=COALESCE(?,hostname),
                last_seen=?,is_online=1 WHERE mac=?""", (ip, hostname, ts, mac))
        conn.execute("INSERT INTO presence (mac,ip,status,seen_at) VALUES (?,?,'online',?)",
            (mac, ip, ts))
    conn.commit(); conn.close()

# ── Host bandwidth ────────────────────────────────────────────────────────────
_last_net = None; _last_net_ts = None
def collect_host_bandwidth():
    global _last_net, _last_net_ts
    c = psutil.net_io_counters(); ts = now()
    if _last_net:
        el   = time.time() - _last_net_ts
        up   = ((c.bytes_sent - _last_net.bytes_sent) * 8) / (el * 1e6) if el else 0
        down = ((c.bytes_recv - _last_net.bytes_recv) * 8) / (el * 1e6) if el else 0
        conn = db()
        conn.execute("INSERT INTO bandwidth_host (ts,mbps_up,mbps_down,bytes_sent,bytes_recv) VALUES (?,?,?,?,?)",
            (ts, up, down, c.bytes_sent, c.bytes_recv))
        conn.commit(); conn.close()
    _last_net = c; _last_net_ts = time.time()

# ── Main ──────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    print("="*60)
    print("  Karakery Monitor  —  run as Administrator")
    print(f"  DB: {DB_PATH}")
    print("="*60)
    init_db()

    iface, our_mac = find_hotspot_iface()
    if not iface:
        print("[ERROR] Hotspot interface not found. Turn on Mobile Hotspot first.")
        exit(1)

    HOTSPOT_MAC = our_mac
    print(f"[NET] Our MAC: {HOTSPOT_MAC}")

    threading.Thread(target=start_capture, args=(iface,), daemon=True).start()

    arp_scan(); collect_host_bandwidth()

    schedule.every(10).seconds.do(flush_counters)
    schedule.every(SCAN_INTERVAL).seconds.do(arp_scan)
    schedule.every(10).seconds.do(collect_host_bandwidth)

    print(f"[OK] Monitoring active. Dashboard -> http://localhost:5000  |  Ctrl+C to stop")
    while True:
        schedule.run_pending()
        time.sleep(1)
