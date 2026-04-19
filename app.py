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

# Increase timeout for slow networks
pyVoIP.SIP_TIMEOUT = 20

phone = None
phone_lock = threading.Lock()

def maintain_connection():
    global phone
    while True:
        with phone_lock:
            if phone is None or phone._status == PhoneStatus.FAILED or phone._status == PhoneStatus.INACTIVE:
                logger.info("Starting/Restarting SIP registration...")
                try:
                    if phone: phone.stop()
                    phone = VoIPPhone(SIP_SERVER, 5060, SIP_USER, SIP_PASS, sipPort=0)
                    phone.start()
                except Exception as e:
                    logger.error(f"Registration Error: {e}")
            
            status = phone._status if phone else "None"
            logger.info(f"Current SIP Status: {status}")
            
        time.sleep(30) # Check status every 30 seconds

@app.route('/')
def index():
    status = str(phone._status).split('.')[-1] if phone else "None"
    return jsonify({"service": "SIP API", "status": status, "instructions": "Use /call?call=NUMBER"})

@app.route('/call', methods=['GET', 'POST'])
def make_call():
    dest = (request.args.get('call') or (request.json.get('destination') if request.is_json else None))
    
    if not dest:
        return jsonify({"error": "Missing 'call' parameter"}), 400

    if not phone or phone._status != PhoneStatus.REGISTERED:
        status = str(phone._status).split('.')[-1] if phone else "None"
        return jsonify({"error": f"SIP not ready. Current Status: {status}. Try again in 10 seconds."}), 503

    try:
        logger.info(f"Calling {dest}...")
        call = phone.call(dest)
        
        def monitor(c, d):
            start = time.time()
            while c.state != CallState.ENDED and (time.time() - start) < 60:
                if c.state == CallState.ANSWERED:
                    logger.info(f"Call {d} Answered. Hanging up.")
                    time.sleep(1)
                    c.hangup()
                    break
                time.sleep(0.5)
            c.hangup()

        threading.Thread(target=monitor, args=(call, dest), daemon=True).start()
        return jsonify({"message": f"Calling {dest}", "status": "Initiated"})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# Start background maintenance thread
threading.Thread(target=maintain_connection, daemon=True).start()

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)
