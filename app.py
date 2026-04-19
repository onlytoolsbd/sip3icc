import os
import time
import threading
import logging
from flask import Flask, request, jsonify
from pyVoIP.VoIP import VoIPPhone, CallState, PhoneStatus
import pyVoIP

# Enable pyVoIP debugging to see SIP packets in Render logs
pyVoIP.DEBUG = True

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')
logger = logging.getLogger(__name__)

app = Flask(__name__)

# SIP Configuration
SIP_SERVER = "sip.icctalk.com"
SIP_USER = "09639187791"
SIP_PASS = "okabye"

# SIP Globals
phone = None
phone_lock = threading.Lock()

def start_sip_client():
    global phone
    with phone_lock:
        if phone is not None:
            try:
                phone.stop()
            except:
                pass
        
        logger.info(f"Initiating SIP for {SIP_USER}...")
        # Use random source port to help bypass firewall/NAT restrictions
        phone = VoIPPhone(SIP_SERVER, 5060, SIP_USER, SIP_PASS, sipPort=0)
        phone.start()

def get_current_status():
    if phone is None:
        return "NONE"
    return str(phone._status).split('.')[-1]

@app.route('/')
def index():
    return jsonify({
        "service": "SIP API",
        "status": get_current_status(),
        "usage": "/call?call=NUMBER"
    })

@app.route('/call', methods=['GET', 'POST'])
def make_call():
    dest = (request.args.get('call') or (request.json.get('destination') if request.is_json else None))
    
    if not dest:
        return jsonify({"error": "Missing 'call' parameter"}), 400

    logger.info(f"Fast Call Request to {dest}. Checking registration...")

    # If disconnected or failed, trigger a start
    if phone is None or phone._status in [PhoneStatus.FAILED, PhoneStatus.INACTIVE]:
        start_sip_client()
        time.sleep(2) # Brief wait for thread to start

    # Wait for up to 10 seconds for REGISTERED
    start_wait = time.time()
    while (time.time() - start_wait) < 10:
        if phone._status == PhoneStatus.REGISTERED:
            logger.info("SIP Registered! Proceeding with call.")
            break
        logger.info(f"Still {get_current_status()}... waiting...")
        time.sleep(1.5)

    # Proceed even if still REGISTERING (Aggressive Mode)
    status = phone._status
    if status not in [PhoneStatus.REGISTERED, PhoneStatus.REGISTERING]:
        return jsonify({"error": "SIP Client not ready", "status": get_current_status()}), 503

    try:
        logger.info(f"Executing call to {dest} (Current Status: {get_current_status()})")
        call = phone.call(dest)
        
        def monitor(c, d):
            m_start = time.time()
            # Monitor for 60 seconds
            while c.state != CallState.ENDED and (time.time() - m_start) < 60:
                if c.state == CallState.ANSWERED:
                    logger.info(f"Call {d} ANSWERED. Hanging up in 1s.")
                    time.sleep(1)
                    c.hangup()
                    break
                time.sleep(0.5)
            try: c.hangup()
            except: pass

        threading.Thread(target=monitor, args=(call, dest), daemon=True).start()
        
        return jsonify({
            "message": f"Calling {dest}",
            "sip_status": get_current_status(),
            "note": "Call attempted immediately"
        })
    except Exception as e:
        logger.error(f"Call initiation failed: {e}")
        return jsonify({"error": str(e), "status": get_current_status()}), 500

# Initial start on boot
threading.Thread(target=start_sip_client, daemon=True).start()

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)
