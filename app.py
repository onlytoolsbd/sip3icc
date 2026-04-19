import os
import time
import threading
import logging
import requests
from flask import Flask, request, jsonify
from pyVoIP.VoIP import VoIPPhone, CallState, PhoneStatus
import pyVoIP

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

# Global Phone Instance
phone = None
phone_lock = threading.Lock()
public_ip = "0.0.0.0"

def get_public_ip():
    try:
        # Try to get public IP to help with SIP NAT traversal
        response = requests.get('https://api.ipify.org', timeout=5)
        return response.text
    except:
        return "0.0.0.0"

def start_sip_client():
    global phone, public_ip
    with phone_lock:
        try:
            if phone:
                phone.stop()
        except:
            pass
        
        public_ip = get_public_ip()
        logger.info(f"Detected Public IP: {public_ip}")
        logger.info(f"Starting SIP for {SIP_USER}...")
        
        # Passing myIP=public_ip can help the SIP server route packets back to us
        phone = VoIPPhone(SIP_SERVER, 5060, SIP_USER, SIP_PASS, myIP=public_ip, sipPort=0)
        phone.start()

def get_current_status():
    if phone is None: return "NONE"
    return str(phone._status).split('.')[-1]

@app.route('/')
def index():
    return jsonify({
        "service": "SIP API",
        "status": get_current_status(),
        "public_ip": public_ip,
        "usage": "/call?call=NUMBER"
    })

@app.route('/call', methods=['GET', 'POST'])
def make_call():
    dest = (request.args.get('call') or (request.json.get('destination') if request.is_json else None))
    
    if not dest:
        return jsonify({"error": "Missing 'call' parameter"}), 400

    logger.info(f"Requesting call to {dest}. Waiting for registration...")

    # Force a restart if status is FAILED or NONE
    if phone is None or phone._status in [PhoneStatus.FAILED, PhoneStatus.INACTIVE]:
        start_sip_client()

    # Wait for up to 25 seconds (blocking the browser request as requested)
    start_wait = time.time()
    while (time.time() - start_wait) < 25:
        if phone and phone._status == PhoneStatus.REGISTERED:
            break
        logger.info(f"Waiting for registration... ({get_current_status()})")
        time.sleep(2)

    if not phone or phone._status != PhoneStatus.REGISTERED:
        return jsonify({
            "error": "Registration Timeout",
            "current_status": get_current_status(),
            "message": "SIP Server is not responding. This usually happens on Render's free tier due to UDP blocking."
        }), 504

    try:
        logger.info(f"Registered! Initiating call to {dest}...")
        call = phone.call(dest)
        
        # Background monitor for auto-hangup
        def monitor(c, d):
            m_start = time.time()
            while c.state != CallState.ENDED and (time.time() - m_start) < 60:
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
            "message": f"Calling {dest}",
            "registration": "SUCCESS",
            "status": "Initiated"
        })
    except Exception as e:
        logger.error(f"Call failed: {e}")
        return jsonify({"error": str(e), "status": get_current_status()}), 500

# Start SIP on boot
threading.Thread(target=start_sip_client, daemon=True).start()

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)
