"""
dashboard.py — Web Dashboard
Run alongside monitor.py.
Open http://localhost:5000 in your browser.
"""

import sqlite3, os, json
from datetime import datetime, timedelta, date
from flask import Flask, jsonify, render_template_string, request

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "netmon.db")
app = Flask(__name__)

def db():
    c = sqlite3.connect(DB_PATH)
    c.row_factory = sqlite3.Row
    return c

# ── API endpoints ─────────────────────────────────────────────────────────────

@app.route("/api/devices")
def api_devices():
    conn = db()
    today = date.today().isoformat()
    rows = conn.execute("""
        SELECT d.mac, d.ip, d.hostname, d.vendor, d.label, d.is_online,
               d.first_seen, d.last_seen,
               COALESCE(dy.bytes_in,  0) AS today_in,
               COALESCE(dy.bytes_out, 0) AS today_out
        FROM devices d
        LEFT JOIN bandwidth_daily dy ON dy.mac = d.mac AND dy.date = ?
        ORDER BY d.is_online DESC, today_in + today_out DESC
    """, (today,)).fetchall()
    conn.close()

    now_dt = datetime.now()
    results = []
    for r in rows:
        d = dict(r)
        # Real-time online verification: if not seen in last 45s, mark offline
        if d["last_seen"]:
            try:
                ls = datetime.strptime(d["last_seen"], "%Y-%m-%d %H:%M:%S")
                diff = int((now_dt - ls).total_seconds())
                if diff > 45:
                    d["is_online"] = 0
                if diff < 10:
                    d["time_ago"] = "active now"
                elif diff < 60:
                    d["time_ago"] = f"{diff}s ago"
                elif diff < 3600:
                    d["time_ago"] = f"{diff // 60}m ago"
                else:
                    d["time_ago"] = f"{diff // 3600}h ago"
            except:
                d["time_ago"] = d["last_seen"]
        else:
            d["is_online"] = 0
            d["time_ago"] = "never"
        results.append(d)

    # Sort: online first, then highest traffic
    results.sort(key=lambda x: (x["is_online"], x["today_in"] + x["today_out"]), reverse=True)
    return jsonify(results)

@app.route("/api/bandwidth/realtime")
def api_realtime():
    conn = db()
    since = (datetime.now() - timedelta(minutes=5)).strftime("%Y-%m-%d %H:%M:%S")
    rows = conn.execute("""
        SELECT ts, mac, ip,
               SUM(bytes_in)  AS bytes_in,
               SUM(bytes_out) AS bytes_out
        FROM bandwidth_realtime
        WHERE ts >= ?
        GROUP BY ts, mac
        ORDER BY ts
    """, (since,)).fetchall()
    conn.close()
    return jsonify([dict(r) for r in rows])

@app.route("/api/bandwidth/daily")
def api_daily():
    conn = db()
    rows = conn.execute("""
        SELECT dy.date, dy.mac,
               COALESCE(d.label, d.hostname, dy.mac) AS name,
               dy.bytes_in, dy.bytes_out
        FROM bandwidth_daily dy
        LEFT JOIN devices d ON d.mac = dy.mac
        WHERE dy.date >= date('now', '-30 days')
        ORDER BY dy.date DESC, dy.bytes_in + dy.bytes_out DESC
    """).fetchall()
    conn.close()
    return jsonify([dict(r) for r in rows])

@app.route("/api/host/bandwidth")
def api_host():
    conn = db()
    since = (datetime.now() - timedelta(minutes=5)).strftime("%Y-%m-%d %H:%M:%S")
    rows = conn.execute("""
        SELECT ts, mbps_up, mbps_down FROM bandwidth_host
        WHERE ts >= ? ORDER BY ts
    """, (since,)).fetchall()
    conn.close()
    return jsonify([dict(r) for r in rows])

@app.route("/api/alerts")
def api_alerts():
    conn = db()
    rows = conn.execute("""
        SELECT a.ts, a.mac, a.message,
               COALESCE(d.label, d.hostname, a.mac) AS name
        FROM alerts a
        LEFT JOIN devices d ON d.mac = a.mac
        ORDER BY a.ts DESC LIMIT 50
    """).fetchall()
    conn.close()
    return jsonify([dict(r) for r in rows])

@app.route("/api/label", methods=["POST"])
def api_label():
    data = request.json
    conn = db()
    conn.execute("UPDATE devices SET label=? WHERE mac=?", (data["label"], data["mac"]))
    conn.commit(); conn.close()
    return jsonify({"ok": True})

@app.route("/api/device/delete", methods=["POST"])
def api_device_delete():
    mac = request.json.get("mac")
    conn = db()
    conn.execute("DELETE FROM devices WHERE mac=?", (mac,))
    conn.execute("DELETE FROM bandwidth_realtime WHERE mac=?", (mac,))
    conn.execute("DELETE FROM bandwidth_daily WHERE mac=?", (mac,))
    conn.commit(); conn.close()
    return jsonify({"ok": True})

@app.route("/api/export/csv")
def api_export():
    import csv, io
    conn = db()
    rows = conn.execute("""
        SELECT dy.date, COALESCE(d.label, d.hostname, dy.mac) AS device,
               dy.mac, dy.bytes_in, dy.bytes_out
        FROM bandwidth_daily dy
        LEFT JOIN devices d ON d.mac = dy.mac
        ORDER BY dy.date, device
    """).fetchall()
    conn.close()
    out = io.StringIO()
    w = csv.writer(out)
    w.writerow(["Date","Device","MAC","Download_Bytes","Upload_Bytes"])
    w.writerows(rows)
    from flask import Response
    return Response(out.getvalue(), mimetype="text/csv",
        headers={"Content-Disposition": "attachment; filename=netmon_export.csv"})

# ── Main HTML page ────────────────────────────────────────────────────────────

HTML = """
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Karakery Monitor</title>
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.0/dist/chart.umd.min.js"></script>
<style>
  :root {
    --bg:      #0d1117;
    --surface: #161b22;
    --card:    #1f2937;
    --border:  #30363d;
    --text:    #e6edf3;
    --sub:     #8b949e;
    --green:   #3fb950;
    --red:     #f85149;
    --blue:    #58a6ff;
    --orange:  #d29922;
    --purple:  #bc8cff;
  }
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body { background: var(--bg); color: var(--text); font-family: 'Segoe UI', system-ui, sans-serif; }

  header {
    background: var(--surface);
    border-bottom: 1px solid var(--border);
    padding: 16px 32px;
    display: flex; align-items: center; justify-content: space-between;
    flex-wrap: wrap; gap: 12px;
  }
  header h1 { font-size: 1.3rem; font-weight: 600; display: flex; align-items: center; gap: 8px; }
  header h1 span { color: var(--blue); }
  .badge { font-size: 0.75rem; background: var(--card); border: 1px solid var(--border);
           padding: 4px 10px; border-radius: 20px; color: var(--sub); }

  .grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(160px, 1fr));
          gap: 16px; padding: 24px 32px 0; }
  .stat { background: var(--card); border: 1px solid var(--border); border-radius: 10px;
          padding: 18px 20px; }
  .stat .label { font-size: 0.75rem; color: var(--sub); margin-bottom: 6px; }
  .stat .value { font-size: 2rem; font-weight: 700; }
  .stat .value.green { color: var(--green); }
  .stat .value.blue  { color: var(--blue); }
  .stat .value.orange{ color: var(--orange); }

  .section { padding: 24px 32px; }
  .section-header { display: flex; align-items: center; justify-content: space-between; margin-bottom: 16px; flex-wrap: wrap; gap: 12px; }
  .section h2 { font-size: 1rem; font-weight: 600; color: var(--sub); text-transform: uppercase; letter-spacing: .05em; }

  .filter-tabs { display: flex; gap: 8px; background: var(--surface); border: 1px solid var(--border); border-radius: 8px; padding: 4px; }
  .filter-tab { background: none; border: none; color: var(--sub); border-radius: 6px; padding: 6px 14px;
                cursor: pointer; font-size: 0.8rem; font-weight: 600; transition: all .2s; }
  .filter-tab.active { background: var(--card); color: var(--text); box-shadow: 0 1px 3px rgba(0,0,0,.3); }
  .filter-tab:hover:not(.active) { color: var(--text); }

  .chart-box { background: var(--card); border: 1px solid var(--border);
               border-radius: 10px; padding: 20px; margin-bottom: 16px; }
  .chart-box canvas { max-height: 200px; }

  table { width: 100%; border-collapse: collapse; font-size: 0.85rem; }
  th { text-align: left; padding: 10px 14px; color: var(--sub);
       font-weight: 500; border-bottom: 1px solid var(--border); }
  td { padding: 10px 14px; border-bottom: 1px solid var(--border); }
  tr:last-child td { border-bottom: none; }
  tr:hover td { background: rgba(255,255,255,.02); }

  .dot { width: 8px; height: 8px; border-radius: 50%; display: inline-block; margin-right: 6px; }
  .dot.online  { background: var(--green); box-shadow: 0 0 8px var(--green); }
  .dot.offline { background: var(--sub); }

  .bar { height: 6px; background: var(--border); border-radius: 3px; overflow: hidden; }
  .bar-fill { height: 100%; background: var(--blue); border-radius: 3px; transition: width .3s; }

  .action-btn { background: none; border: 1px solid var(--border); color: var(--sub);
                border-radius: 6px; padding: 4px 8px; cursor: pointer; font-size: 0.75rem; transition: .2s; }
  .action-btn:hover { border-color: var(--blue); color: var(--blue); }
  .del-btn:hover { border-color: var(--red); color: var(--red); }

  .alert-item { background: var(--card); border: 1px solid var(--border);
                border-left: 3px solid var(--orange);
                border-radius: 8px; padding: 10px 14px; margin-bottom: 8px; font-size: 0.85rem; }
  .alert-item .time { color: var(--sub); font-size: 0.75rem; }

  .btn { background: var(--card); border: 1px solid var(--border); color: var(--text);
         border-radius: 8px; padding: 7px 14px; cursor: pointer; font-size: 0.82rem;
         text-decoration: none; display: inline-flex; align-items: center; gap: 6px; }
  .btn:hover { border-color: var(--blue); color: var(--blue); }

  #refresh-indicator { font-size: 0.75rem; color: var(--sub); }
  .empty-row td { text-align: center; padding: 32px; color: var(--sub); }
</style>
</head>
<body>

<header>
  <h1>🌐 <span>Karakery</span> Monitor</h1>
  <div style="display:flex;gap:10px;align-items:center">
    <span id="refresh-indicator">Auto-refresh (2s)</span>
    <button onclick="refresh()" class="btn">🔄 Refresh</button>
    <a href="/api/export/csv" class="btn">⬇ Export CSV</a>
  </div>
</header>

<div class="grid" id="stats"></div>

<div class="section">
  <h2>Laptop Bandwidth (Live)</h2>
  <div class="chart-box"><canvas id="hostChart"></canvas></div>
</div>

<div class="section">
  <div class="section-header">
    <h2>Devices</h2>
    <div class="filter-tabs">
      <button id="tabConnected" class="filter-tab active" onclick="setFilter('connected')">
        🟢 Connected (<span id="countOnline">0</span>)
      </button>
      <button id="tabAll" class="filter-tab" onclick="setFilter('all')">
        📋 All Devices (<span id="countTotal">0</span>)
      </button>
    </div>
  </div>

  <div class="chart-box" style="padding:0;overflow:hidden">
    <table id="devTable">
      <thead><tr>
        <th>Status</th><th>Device</th><th>IP</th><th>MAC</th>
        <th>Vendor</th><th>Last Active</th><th>Today ↓</th><th>Today ↑</th><th>Usage</th><th>Action</th>
      </tr></thead>
      <tbody id="devBody"></tbody>
    </table>
  </div>
</div>

<div class="section">
  <h2>Alerts</h2>
  <div id="alerts"></div>
</div>

<script>
let currentFilter = 'connected';
let allDevices = [];

function setFilter(filter) {
  currentFilter = filter;
  document.getElementById('tabConnected').classList.toggle('active', filter === 'connected');
  document.getElementById('tabAll').classList.toggle('active', filter === 'all');
  renderDevicesTable();
}

const fmt = b => b < 1e6 ? (b/1e3).toFixed(1)+' KB'
               : b < 1e9 ? (b/1e6).toFixed(1)+' MB'
               :            (b/1e9).toFixed(2)+' GB';

// Host bandwidth chart
const hostCtx = document.getElementById('hostChart').getContext('2d');
const hostChart = new Chart(hostCtx, {
  type: 'line',
  data: {
    labels: [],
    datasets: [
      { label: 'Download (Mbps)', data: [], borderColor: '#58a6ff', backgroundColor: 'rgba(88,166,255,.1)',
        fill: true, tension: 0.4, pointRadius: 0 },
      { label: 'Upload (Mbps)',   data: [], borderColor: '#3fb950', backgroundColor: 'rgba(63,185,80,.1)',
        fill: true, tension: 0.4, pointRadius: 0 }
    ]
  },
  options: {
    animation: false, responsive: true, maintainAspectRatio: true,
    plugins: { legend: { labels: { color: '#8b949e', font: { size: 12 } } } },
    scales: {
      x: { ticks: { color: '#8b949e', maxTicksLimit: 8 }, grid: { color: '#30363d' } },
      y: { ticks: { color: '#8b949e' }, grid: { color: '#30363d' }, min: 0 }
    }
  }
});

function updateHostChart(data) {
  const labels = data.map(d => d.ts.split(' ')[1]);
  hostChart.data.labels = labels;
  hostChart.data.datasets[0].data = data.map(d => +d.mbps_down.toFixed(3));
  hostChart.data.datasets[1].data = data.map(d => +d.mbps_up.toFixed(3));
  hostChart.update();
}

function updateDevices(devices) {
  allDevices = devices;
  const onlineCount = devices.filter(d => d.is_online).length;
  document.getElementById('countOnline').textContent = onlineCount;
  document.getElementById('countTotal').textContent = devices.length;

  const totalDL = devices.reduce((s, d) => s + d.today_in,  0);
  const totalUL = devices.reduce((s, d) => s + d.today_out, 0);

  document.getElementById('stats').innerHTML = `
    <div class="stat"><div class="label">Devices Connected</div><div class="value green">${onlineCount}</div></div>
    <div class="stat"><div class="label">Total Devices</div><div class="value blue">${devices.length}</div></div>
    <div class="stat"><div class="label">Today Download</div><div class="value blue">${fmt(totalDL)}</div></div>
    <div class="stat"><div class="label">Today Upload</div><div class="value orange">${fmt(totalUL)}</div></div>
  `;

  renderDevicesTable();
}

function renderDevicesTable() {
  const tbody = document.getElementById('devBody');
  const maxToday = Math.max(1, ...allDevices.map(d => d.today_in + d.today_out));
  
  // Filter devices: if 'connected', only show is_online == 1
  const displayed = currentFilter === 'connected' 
    ? allDevices.filter(d => d.is_online)
    : allDevices;

  if (displayed.length === 0) {
    tbody.innerHTML = `<tr class="empty-row"><td colspan="10">No devices in this view.</td></tr>`;
    return;
  }

  tbody.innerHTML = displayed.map(d => {
    const name    = d.label || d.hostname || d.mac;
    const pct     = ((d.today_in + d.today_out) / maxToday * 100).toFixed(1);
    const status  = d.is_online ? 'online' : 'offline';
    const statusText = d.is_online ? 'ONLINE' : 'OFFLINE';

    return `<tr>
      <td><span class="dot ${status}"></span><strong style="font-size:.78rem;color:${d.is_online?'#3fb950':'#8b949e'}">${statusText}</strong></td>
      <td><strong>${name}</strong></td>
      <td style="font-family:monospace;color:#8b949e">${d.ip || '—'}</td>
      <td style="font-family:monospace;font-size:.8rem;color:#8b949e">${d.mac}</td>
      <td style="color:#8b949e">${d.vendor || '—'}</td>
      <td style="font-size:.8rem;color:#8b949e">${d.time_ago || '—'}</td>
      <td style="color:#58a6ff">${fmt(d.today_in)}</td>
      <td style="color:#3fb950">${fmt(d.today_out)}</td>
      <td style="width:110px"><div class="bar"><div class="bar-fill" style="width:${pct}%"></div></div></td>
      <td style="white-space:nowrap">
        <button class="action-btn" onclick="labelDevice('${d.mac}','${name}')">✏ Label</button>
        ${!d.is_online ? `<button class="action-btn del-btn" onclick="deleteDevice('${d.mac}','${name}')">🗑</button>` : ''}
      </td>
    </tr>`;
  }).join('');
}

function updateAlerts(alerts) {
  document.getElementById('alerts').innerHTML = alerts.slice(0,10).map(a =>
    `<div class="alert-item">
       <div class="time">${a.ts}</div>
       <div>${a.message}</div>
     </div>`
  ).join('') || '<div style="color:#8b949e;font-size:.85rem">No alerts yet.</div>';
}

function labelDevice(mac, current) {
  const label = prompt(`Label for ${mac}:`, current);
  if (!label) return;
  fetch('/api/label', { method: 'POST',
    headers: {'Content-Type':'application/json'},
    body: JSON.stringify({mac, label}) }).then(() => refresh());
}

function deleteDevice(mac, name) {
  if (!confirm(`Remove ${name} (${mac}) from history?`)) return;
  fetch('/api/device/delete', { method: 'POST',
    headers: {'Content-Type':'application/json'},
    body: JSON.stringify({mac}) }).then(() => refresh());
}

async function refresh() {
  try {
    const [devs, host, alerts] = await Promise.all([
      fetch('/api/devices').then(r => r.json()),
      fetch('/api/host/bandwidth').then(r => r.json()),
      fetch('/api/alerts').then(r => r.json()),
    ]);
    updateDevices(devs);
    updateHostChart(host);
    updateAlerts(alerts);
    document.getElementById('refresh-indicator').textContent =
      'Live • ' + new Date().toLocaleTimeString();
  } catch(e) {
    document.getElementById('refresh-indicator').textContent = 'Error — is monitor.py running?';
  }
}

refresh();
setInterval(refresh, 2000);
</script>
</body>
</html>
"""

@app.route("/")
def index():
    return render_template_string(HTML)

if __name__ == "__main__":
    print("[Dashboard] http://localhost:5000")
    app.run(host="0.0.0.0", port=5000, debug=False)
