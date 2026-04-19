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
RAW_PROXIES = [
    "203.95.220.218:1080|w8t|w8t",
    "103.135.252.26:1080|w8t|w8t",
    "103.151.169.187:1080|w8t|w8t",
    "103.84.38.42:1080|w8t|w8t"
]

# Global State
phone = None
phone_lock = threading.Lock()
current_proxy_info = None
ranked_proxies = [] # List of (proxy_string, latency)
proxy_index = 0

def test_proxies():
    """Test all proxies for latency and rank them."""
    global ranked_proxies
    results = []
    logger.info("Testing proxy latencies to find the best connection...")
    
    for p_str in RAW_PROXIES:
        addr_part = p_str.split('|')[0]
        host, port = addr_part.split(':')
        
        start = time.time()
        try:
            # Simple TCP connection test to the proxy port
            with socket.create_connection((host, int(port)), timeout=3):
                latency = (time.time() - start) * 1000
                results.append((p_str, latency))
                logger.info(f"Proxy {addr_part} responded in {latency:.2f}ms")
        except Exception as e:
            logger.warning(f"Proxy {addr_part} failed latency test: {e}")
            results.append((p_str, 9999)) # Mark as very slow/failed

    # Sort by latency (lowest first)
    results.sort(key=lambda x: x[1])
    ranked_proxies = [r[0] for r in results]
    logger.info(f"Proxies ranked. Best: {ranked_proxies[0].split('|')[0]}")

def setup_proxy():
    global current_proxy_info, proxy_index
    
    if not ranked_proxies:
        test_proxies()

    # Pick the next proxy in the ranked list (starting with the best)
    proxy_str = ranked_proxies[proxy_index % len(ranked_proxies)]
    addr_part, user, pw = proxy_str.split('|')
    host, port = addr_part.split(':')
    
    current_proxy_info = {
        "address": addr_part,
        "rank": (proxy_index % len(ranked_proxies)) + 1
    }
    
    logger.info(f"Connecting via Best Proxy #{current_proxy_info['rank']}: {addr_part}")
    
    # Apply SOCKS5 proxy settings
    socks.set_default_proxy(socks.SOCKS5, host, int(port), True, user, pw)
    # Monkeypatch
    socket.socket = socks.socksocket
    pyVoIP.SIP.socket.socket = socks.socksocket
    
    proxy_index += 1 # Prepare next proxy for fallback

def start_sip_client():
    global phone
    setup_proxy()
    
    with phone_lock:
        try:
            if phone:
                phone.stop()
                time.sleep(1)
        except: pass
        
        logger.info(f"Starting SIP for {SIP_USER} via Proxy...")
        phone = VoIPPhone(SIP_SERVER, 5060, SIP_USER, SIP_PASS, myIP="0.0.0.0", sipPort=0)
        phone.start()

def get_current_status():
    if phone is None: return "NONE"
    return str(phone._status).split('.')[-1]

@app.route('/')
def index():
    return jsonify({
        "service": "SIP API - Best Proxy Mode",
        "status": get_current_status(),
        "proxy": current_proxy_info,
        "usage": "/call?call=NUMBER"
    })

@app.route('/call', methods=['GET', 'POST'])
def make_call():
    dest = (request.args.get('call') or (request.json.get('destination') if request.is_json else None))
    
    if not dest:
        return jsonify({"error": "Missing 'call' parameter"}), 400

    logger.info(f"Call Request to {dest}. Rank Check...")

    if phone is None or phone._status in [PhoneStatus.FAILED, PhoneStatus.INACTIVE]:
        start_sip_client()

    # Wait for up to 30 seconds
    start_wait = time.time()
    while (time.time() - start_wait) < 30:
        status = phone._status if phone else None
        if status == PhoneStatus.REGISTERED:
            break
        
        if status == PhoneStatus.FAILED:
            logger.warning("Fastest proxy failed registration. Trying next best...")
            start_sip_client()
            time.sleep(2)
        
        logger.info(f"Waiting for registration... Status: {get_current_status()}")
        time.sleep(2)

    if not phone or phone._status != PhoneStatus.REGISTERED:
        return jsonify({
            "error": "Registration Timeout",
            "current_status": get_current_status(),
            "proxy": current_proxy_info,
            "message": "Failed to connect via top proxies. Try again to rotate."
        }), 504

    try:
        logger.info(f"Registered via best proxy! Calling {dest}...")
        call = phone.call(dest)
        
        def monitor(c, d):
            m_start = time.time()
            while c.state != CallState.ENDED and (time.time() - m_start) < 90:
                if c.state == CallState.ANSWERED:
                    logger.info(f"Call {d} ANSWERED. Hanging up.")
                    time.sleep(1)
                    c.hangup()
                    break
                time.sleep(0.5)
            try: c.hangup()
            except: pass

        threading.Thread(target=monitor, args=(call, dest), daemon=True).start()
        
        return jsonify({
            "message": f"Calling {dest}",
            "registration": "SUCCESS",
            "proxy_used": current_proxy_info
        })
    except Exception as e:
        logger.error(f"Call initiation error: {e}")
        return jsonify({"error": str(e), "status": get_current_status()}), 500

# Perform initial latency test and start SIP
def boot():
    test_proxies()
    start_sip_client()

threading.Thread(target=boot, daemon=True).start()

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)
