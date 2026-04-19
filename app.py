import os
import time
import threading
import logging
import random
import socket
from flask import Flask, request, jsonify
from pyVoIP.VoIP import VoIPPhone, CallState, PhoneStatus
import pyVoIP
import socks # From PySocks

# Enable pyVoIP debugging
pyVoIP.DEBUG = True

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')
logger = logging.getLogger(__name__)

app = Flask(__name__)

# SIP Configuration
SIP_SERVER = "sip.icctalk.com"
SIP_USER = "09639187791"
SIP_PASS = "okabye"

# SOCKS5 Proxy List (IP:PORT|USER|PASS)
PROXIES = [
    "203.95.220.218:1080|w8t|w8t",
    "103.135.252.26:1080|w8t|w8t",
    "103.151.169.187:1080|w8t|w8t",
    "103.84.38.42:1080|w8t|w8t"
]

# Global Phone Instance
phone = None
phone_lock = threading.Lock()
current_proxy = None

def setup_proxy():
    global current_proxy
    proxy_str = random.choice(PROXIES)
    addr_part, user, pw = proxy_str.split('|')
    host, port = addr_part.split(':')
    
    current_proxy = addr_part
    logger.info(f"Connecting via SOCKS5 Proxy: {host}:{port} (User: {user})")
    
    # Monkey-patch socket to use SOCKS5
    socks.set_default_proxy(socks.SOCKS5, host, int(port), True, user, pw)
    socket.socket = socks.socksocket

def start_sip_client():
    global phone
    setup_proxy() # Select new random proxy on each start
    
    with phone_lock:
        try:
            if phone:
                logger.info("Stopping old SIP instance...")
                phone.stop()
        except:
            pass
        
        logger.info(f"Starting SIP for {SIP_USER} via Proxy...")
        # CRITICAL FIX: myIP must be "0.0.0.0" on Render/Linux to avoid Errno 99
        phone = VoIPPhone(SIP_SERVER, 5060, SIP_USER, SIP_PASS, myIP="0.0.0.0", sipPort=0)
        phone.start()

def get_current_status():
    if phone is None: return "NONE"
    return str(phone._status).split('.')[-1]

@app.route('/')
def index():
    return jsonify({
        "service": "SIP API with SOCKS5",
        "status": get_current_status(),
        "proxy_in_use": current_proxy,
        "usage": "/call?call=NUMBER"
    })

@app.route('/call', methods=['GET', 'POST'])
def make_call():
    dest = (request.args.get('call') or (request.json.get('destination') if request.is_json else None))
    
    if not dest:
        return jsonify({"error": "Missing 'call' parameter"}), 400

    logger.info(f"Request to call {dest}. Checking proxy registration...")

    # Restart if failed or none
    if phone is None or phone._status in [PhoneStatus.FAILED, PhoneStatus.INACTIVE]:
        start_sip_client()

    # Wait for up to 25 seconds
    start_wait = time.time()
    while (time.time() - start_wait) < 25:
        if phone and phone._status == PhoneStatus.REGISTERED:
            break
        logger.info(f"Waiting for proxy registration... ({get_current_status()})")
        time.sleep(2)

    if not phone or phone._status != PhoneStatus.REGISTERED:
        return jsonify({
            "error": "Proxy/SIP Registration Timeout",
            "current_status": get_current_status(),
            "proxy": current_proxy,
            "message": "The proxy may not support UDP or the SIP server is unreachable."
        }), 504

    try:
        logger.info(f"Initiating call to {dest} via Proxy...")
        call = phone.call(dest)
        
        def monitor(c, d):
            m_start = time.time()
            while c.state != CallState.ENDED and (time.time() - m_start) < 90:
                if c.state == CallState.ANSWERED:
                    logger.info(f"Call {d} Answered. Hanging up in 1s.")
                    time.sleep(1)
                    c.hangup()
                    break
                time.sleep(0.5)
            try: c.hangup()
            except: pass

        threading.Thread(target=monitor, args=(call, dest), daemon=True).start()
        
        return jsonify({
            "message": f"Calling {dest} via SOCKS5",
            "registration": "SUCCESS",
            "proxy": current_proxy
        })
    except Exception as e:
        logger.error(f"Proxy call failed: {e}")
        return jsonify({"error": str(e), "status": get_current_status()}), 500

# Start on boot
threading.Thread(target=start_sip_client, daemon=True).start()

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)
