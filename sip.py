from flask import Flask, request, jsonify, render_template_string, session, redirect, url_for
import threading
import time
import socket
import socks
import random
import sys
import json
import os
import concurrent.futures
from datetime import datetime
from pyVoIP.VoIP import VoIPPhone, CallState, PhoneStatus

# --- CONFIG MANAGEMENT ---
CONFIG_FILE = "config.json"
CALL_LOGS = [] 

def load_config():
    if not os.path.exists(CONFIG_FILE):
        return {"accounts": [], "proxies": [], "admin_password": "admin", "default_server": "sip.icctalk.com"}
    with open(CONFIG_FILE, "r") as f:
        config = json.load(f)
        if "default_server" not in config:
            config["default_server"] = "sip.icctalk.com"
        return config

def save_config(config):
    with open(CONFIG_FILE, "w") as f:
        json.dump(config, f, indent=4)

def add_log(number, status, account, server, proxy):
    global CALL_LOGS
    log_entry = {
        "time": datetime.now().strftime("%H:%M:%S"),
        "number": number,
        "status": status,
        "account": account,
        "server": server,
        "proxy": proxy
    }
    CALL_LOGS.insert(0, log_entry)
    if len(CALL_LOGS) > 100:
        CALL_LOGS.pop()

# --- ADVANCED PROXY MONKEY PATCH (Thread-Safe) ---
thread_local = threading.local()
_orig_socket = socket.socket

class ProxySocket(socks.socksocket):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Check if this thread has a specific proxy assigned
        proxy_data = getattr(thread_local, 'proxy', None)
        if proxy_data:
            self.set_proxy(socks.SOCKS5, proxy_data['ip'], proxy_data['port'], True, proxy_data['user'], proxy_data['pw'])

# Apply the patch globally
socket.socket = ProxySocket

def set_thread_proxy():
    """Assigns a random proxy to the current thread's local storage."""
    config = load_config()
    proxies = config.get("proxies", [])
    if not proxies:
        thread_local.proxy = None
        return "Direct"
    
    proxy_str = random.choice(proxies)
    try:
        ip_port, user, pw = proxy_str.split('|')
        ip, port = ip_port.split(':')
        thread_local.proxy = {
            'ip': ip,
            'port': int(port),
            'user': user,
            'pw': pw
        }
        return f"{ip}:{port}"
    except Exception:
        thread_local.proxy = None
        return "Error"

# --- MONKEY PATCH FOR pyVoIP CASE-SENSITIVE HEADERS BUG ---
class CaseInsensitiveDict(dict):
    def __getitem__(self, key):
        if isinstance(key, str):
            low_key = key.lower()
            for k in list(self.keys()):
                if k.lower() == low_key:
                    return super().__getitem__(k)
        return super().__getitem__(key)
    def __contains__(self, key):
        if isinstance(key, str):
            low_key = key.lower()
            for k in self.keys():
                if k.lower() == low_key:
                    return True
        return super().__contains__(key)
    def get(self, key, default=None):
        try:
            return self[key]
        except KeyError:
            return default

def apply_pyvoip_patch():
    try:
        import pyVoIP.SIP
        _orig_init = pyVoIP.SIP.SIPMessage.__init__
        def _patched_init(self, data):
            _orig_init(self, data)
            new_headers = CaseInsensitiveDict()
            for k, v in self.headers.items():
                new_headers[k] = v
            self.headers = new_headers
        pyVoIP.SIP.SIPMessage.__init__ = _patched_init
    except Exception:
        pass

apply_pyvoip_patch()
# ---------------------------------------------------------

app = Flask(__name__)
app.secret_key = "sip_secret_key_change_me"

# High Concurrency Call Management
executor = concurrent.futures.ThreadPoolExecutor(max_workers=300)
call_semaphore = threading.Semaphore(150) 

# --- ADMIN PANEL ---

ADMIN_HTML = """
<!DOCTYPE html>
<html>
<head>
    <title>SIP ULTRA BLAST</title>
    <link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <style>
        .extra-small { font-size: 0.65rem; }
        .log-entry { animation: slideIn 0.3s ease-out; border-left: 4px solid transparent; }
        @keyframes slideIn { from { transform: translateX(20px); opacity: 0; } to { transform: translateX(0); opacity: 1; } }
        .bg-answered { border-left-color: #198754; background-color: #f0fff4 !important; }
        .bg-failed { border-left-color: #dc3545; background-color: #fff5f5 !important; }
        .bg-progress { border-left-color: #0dcaf0; }
    </style>
</head>
<body class="bg-light">
    <nav class="navbar navbar-dark bg-dark mb-4 shadow">
        <div class="container">
            <span class="navbar-brand fw-bold text-danger">🔥 ULTRA BLAST CONTROL</span>
            <div class="d-flex align-items-center">
                <span class="badge bg-success me-3">SYSTEM ONLINE</span>
                <a href="/admin/logout" class="btn btn-outline-light btn-sm">Logout</a>
            </div>
        </div>
    </nav>

    <div class="container">
        <div class="row">
            <div class="col-lg-7">
                <form method="POST" action="/admin/save">
                    <div class="card mb-4 shadow-sm border-0">
                        <div class="card-header bg-primary text-white fw-bold">SIP Accounts</div>
                        <div class="card-body">
                            <textarea name="accounts" class="form-control font-monospace" rows="12" style="font-size: 0.85rem;">{% for acc in config.accounts %}{{ acc.server }},{{ acc.username }},{{ acc.password }}\n{% endfor %}</textarea>
                        </div>
                    </div>
                    
                    <div class="card mb-4 shadow-sm border-0">
                        <div class="card-header bg-secondary text-white fw-bold">Proxies & Global Settings</div>
                        <div class="card-body">
                            <div class="row">
                                <div class="col-md-12 mb-3">
                                    <label class="small fw-bold">Proxies (Rotating per Account)</label>
                                    <textarea name="proxies" class="form-control font-monospace" rows="4">{% for proxy in config.proxies %}{{ proxy }}\n{% endfor %}</textarea>
                                </div>
                                <div class="col-md-6">
                                    <label class="small fw-bold">Default Server</label>
                                    <input type="text" name="default_server" class="form-control" value="{{ config.default_server }}">
                                </div>
                                <div class="col-md-6">
                                    <label class="small fw-bold">Admin Password</label>
                                    <input type="password" name="admin_password" class="form-control" value="{{ config.admin_password }}">
                                </div>
                            </div>
                        </div>
                    </div>
                    <button type="submit" class="btn btn-primary w-100 py-3 mb-4 shadow fw-bold">SAVE & DEPLOY</button>
                </form>
            </div>

            <div class="col-lg-5">
                <div class="card mb-4 shadow-lg border-danger border-2">
                    <div class="card-header bg-danger text-white text-center fw-bold">ACTIVATE TOTAL BLAST</div>
                    <div class="card-body">
                        <div class="mb-3">
                            <label class="small fw-bold">Target Numbers (One per line)</label>
                            <textarea id="callNum" class="form-control" rows="5" placeholder="88017...
88018..."></textarea>
                        </div>
                        <button class="btn btn-danger w-100 py-2 fw-bold" onclick="triggerCall()">FIRE TOTAL BLAST!</button>
                        <p class="text-muted small mt-2 text-center">Every account will blast every number simultaneously using rotating proxies.</p>
                    </div>
                </div>

                <div class="card shadow-sm border-0">
                    <div class="card-header bg-dark text-white d-flex justify-content-between align-items-center">
                        <span class="fw-bold">Live Attack Logs</span>
                        <button class="btn btn-outline-info btn-sm" onclick="clearLogs()">Clear Logs</button>
                    </div>
                    <div class="card-body p-0">
                        <div id="logList" class="list-group list-group-flush" style="max-height: 600px; overflow-y: auto;"></div>
                    </div>
                </div>
            </div>
        </div>
    </div>

    <script>
    function triggerCall() {
        const num = document.getElementById('callNum').value;
        if(!num) return alert('Enter target number(s)');
        
        let formData = new FormData();
        formData.append('call', num);

        fetch('/call', {
            method: 'POST',
            body: formData
        }).then(res => res.json()).then(data => {
            console.log('Blast started:', data);
        });

        const btn = document.querySelector('.btn-danger');
        btn.disabled = true; btn.innerText = 'BLASTING...';
        setTimeout(() => { btn.disabled = false; btn.innerText = 'FIRE TOTAL BLAST!'; }, 5000);
    }

    function clearLogs() {
        fetch('/admin/clear_logs').then(() => updateLogs());
    }

    function updateLogs() {
        fetch('/admin/logs')
            .then(res => res.json())
            .then(logs => {
                const logList = document.getElementById('logList');
                logList.innerHTML = logs.map(log => {
                    let statusClass = 'bg-progress';
                    if(log.status.includes('Answered')) statusClass = 'bg-answered';
                    else if(log.status.includes('Error') || log.status.includes('Failed')) statusClass = 'bg-failed';
                    
                    return `
                    <div class="list-group-item p-2 log-entry ${statusClass}">
                        <div class="d-flex justify-content-between align-items-center">
                            <strong class="text-primary">${log.number}</strong>
                            <span class="badge bg-light text-dark extra-small">${log.time}</span>
                        </div>
                        <div class="extra-small text-muted">Acc: ${log.account} | Server: ${log.server}</div>
                        <div class="small fw-bold">${log.status}</div>
                    </div>
                `}).join('');
            });
    }

    setInterval(updateLogs, 1500);
    updateLogs();
    </script>
</body>
</html>
"""

LOGIN_HTML = """
<!DOCTYPE html>
<html>
<head>
    <title>Login</title>
    <link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css">
</head>
<body class="bg-light">
    <div class="container mt-5">
        <div class="row justify-content-center">
            <div class="col-md-4">
                <div class="card shadow mt-5 border-0">
                    <div class="card-header bg-danger text-white text-center fw-bold">Admin Portal</div>
                    <div class="card-body">
                        <form method="POST">
                            <div class="mb-3">
                                <label class="form-label">System Password</label>
                                <input type="password" name="password" class="form-control" required>
                            </div>
                            <button type="submit" class="btn btn-danger w-100 fw-bold">AUTHENTICATE</button>
                        </form>
                    </div>
                </div>
            </div>
        </div>
    </div>
</body>
</html>
"""

@app.route('/admin', methods=['GET', 'POST'])
def admin():
    config = load_config()
    if request.method == 'POST':
        if request.form.get('password') == config.get('admin_password'):
            session['admin_logged_in'] = True
            return redirect(url_for('admin'))
        else:
            return "Unauthorized", 401
    if not session.get('admin_logged_in'):
        return render_template_string(LOGIN_HTML)
    return render_template_string(ADMIN_HTML, config=config)

@app.route('/admin/logs')
def get_logs():
    if not session.get('admin_logged_in'):
        return jsonify([])
    return jsonify(CALL_LOGS)

@app.route('/admin/clear_logs')
def clear_logs():
    if not session.get('admin_logged_in'):
        return jsonify({"status": "error"}), 401
    global CALL_LOGS
    CALL_LOGS = []
    return jsonify({"status": "success"})

@app.route('/admin/save', methods=['POST'])
def admin_save():
    if not session.get('admin_logged_in'):
        return redirect(url_for('admin'))
    
    config = {
        "admin_password": request.form.get('admin_password'),
        "default_server": request.form.get('default_server', 'sip.icctalk.com').strip(),
        "proxies": [p.strip() for p in request.form.get('proxies').strip().split('\n') if p.strip()],
        "accounts": []
    }
    
    accounts_raw = request.form.get('accounts').strip().split('\n')
    for line in accounts_raw:
        line = line.strip()
        if not line: continue
        parts = line.split(',')
        if len(parts) == 3:
            config["accounts"].append({"server": parts[0].strip(), "username": parts[1].strip(), "password": parts[2].strip()})
        elif ':' in line:
            parts = line.split(':')
            if len(parts) >= 2:
                u, p = parts[0].strip(), parts[1].strip()
                config["accounts"].append({"server": config["default_server"], "username": u, "password": "" if p.upper() == "NULL" else p})
    
    save_config(config)
    return redirect(url_for('admin'))

@app.route('/admin/logout')
def logout():
    session.pop('admin_logged_in', None)
    return redirect(url_for('admin'))

# --- ASYNC BLAST LOGIC ---

def run_single_account_call(target_number, acc):
    with call_semaphore:
        sip_server, sip_user, sip_pass = acc['server'], acc['username'], acc['password']
        
        # 1. Setup per-thread unique proxy
        proxy_used = set_thread_proxy()
        
        # 2. Setup per-thread unique ports
        local_sip_port = random.randint(10000, 60000)
        rtp_low = random.randint(10000, 30000)
        rtp_high = rtp_low + 50
        
        try:
            phone = VoIPPhone(sip_server, 5060, sip_user, sip_pass, sipPort=local_sip_port, rtpPortLow=rtp_low, rtpPortHigh=rtp_high)
            phone.start()

            # Wait for registration
            timeout, elapsed = 12, 0
            while phone._status != PhoneStatus.REGISTERED and elapsed < timeout:
                time.sleep(1); elapsed += 1

            if phone._status != PhoneStatus.REGISTERED:
                status_msg = f"Reg Failed ({phone._status})"
                phone.stop()
                add_log(target_number, status_msg, sip_user, sip_server, proxy_used)
                return

            call = phone.call(target_number)
            
            # Monitoring call
            timeout, elapsed = 20, 0
            status = "Waiting..."
            while elapsed < timeout:
                if call.state == CallState.ANSWERED:
                    status = "Success: Answered"
                    time.sleep(4) # Keep line for 4s
                    call.hangup()
                    break
                elif call.state == CallState.ENDED:
                    status = "Status: Hung Up/Rejected"
                    break
                time.sleep(1); elapsed += 1
            
            if call.state != CallState.ENDED:
                call.hangup()
                if status == "Waiting...": status = "Status: No Answer"

            phone.stop()
            add_log(target_number, status, sip_user, sip_server, proxy_used)

        except Exception as e:
            add_log(target_number, f"System Error: {str(e)}", sip_user, sip_server, proxy_used)

@app.route('/', methods=['GET'])
@app.route('/call', methods=['GET', 'POST'])
def make_call():
    if request.method == 'POST':
        target_input = request.form.get('call')
    else:
        target_input = request.args.get('call')

    if not target_input:
        return jsonify({"status": "error", "message": "No number(s)"}), 400

    # Handle multiple numbers (one per line)
    numbers = [n.strip() for n in target_input.split('\n') if n.strip()]
    
    config = load_config()
    accounts = config.get("accounts", [])
    if not accounts: return jsonify({"status": "error", "message": "No accounts"}), 500

    # Trigger ALL accounts for ALL numbers simultaneously
    total_triggered = 0
    for target_number in numbers:
        if target_number == 'জান': target_number = '+8801858687390'
        for acc in accounts:
            executor.submit(run_single_account_call, target_number, acc)
            total_triggered += 1
    
    return jsonify({"status": "ULTRA_BLAST_READY", "triggered_calls": total_triggered, "numbers_count": len(numbers)})


if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
