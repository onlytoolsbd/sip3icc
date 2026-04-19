import os
import time
import threading
import logging
from flask import Flask, request, jsonify
from pyVoIP.VoIP import VoIPPhone, CallState, PhoneStatus
import pyVoIP

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
        
        logger.info(f"Starting SIP registration for {SIP_USER}...")
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

    logger.info(f"Request to call {dest}. Checking registration...")

    # Aggressive Registration Wait: Wait up to 30 seconds for REGISTERED status
    start_time = time.time()
    while (time.time() - start_time) < 30:
        status = phone._status if phone else None
        
        if status == PhoneStatus.REGISTERED:
            break
            
        if status in [None, PhoneStatus.FAILED, PhoneStatus.INACTIVE]:
            logger.info("SIP not active, triggering immediate registration...")
            threading.Thread(target=start_sip_client, daemon=True).start()
            
        logger.info(f"Waiting for registration... Current: {get_current_status()}")
        time.sleep(2)

    # Final check after waiting
    if not phone or phone._status != PhoneStatus.REGISTERED:
        return jsonify({
            "error": "Registration Timeout",
            "current_status": get_current_status(),
            "message": "The server is taking too long to register. Please try again."
        }), 504

    try:
        logger.info(f"SIP Registered! Initiating call to {dest}...")
        call = phone.call(dest)
        
        def monitor(c, d):
            m_start = time.time()
            # Monitor for 90 seconds
            while c.state != CallState.ENDED and (time.time() - m_start) < 90:
                if c.state == CallState.ANSWERED:
                    logger.info(f"Call {d} Answered. Hanging up in 1s.")
                    time.sleep(1)
                    c.hangup()
                    break
                time.sleep(0.5)
            try:
                c.hangup()
            except:
                pass
            logger.info(f"Monitor ended for {d}")

        threading.Thread(target=monitor, args=(call, dest), daemon=True).start()
        
        return jsonify({
            "message": f"Calling {dest}",
            "status": "Initiated",
            "registration": "OK"
        })
    except Exception as e:
        logger.exception("Call initiation failed")
        return jsonify({"error": str(e)}), 500

# Initial start
threading.Thread(target=start_sip_client, daemon=True).start()

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)
