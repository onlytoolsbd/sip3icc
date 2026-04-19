import os
import time
import threading
import logging
from flask import Flask, request, jsonify
from pyVoIP.VoIP import VoIPPhone, CallState, PhoneStatus

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s'
)
logger = logging.getLogger(__name__)

app = Flask(__name__)

# SIP Configuration
SIP_SERVER = "sip.icctalk.com"
SIP_USER = "09639187791"
SIP_PASS = "okabye"

# Global Phone Instance
phone = None
phone_lock = threading.Lock()

def init_sip():
    global phone
    with phone_lock:
        if phone is None:
            logger.info(f"Starting SIP client for {SIP_USER}@{SIP_SERVER}...")
            try:
                # sipPort=0 picks a random port, helping bypass some firewall blocks
                phone = VoIPPhone(SIP_SERVER, 5060, SIP_USER, SIP_PASS, sipPort=0)
                phone.start()
                logger.info("SIP Thread started.")
            except Exception as e:
                logger.error(f"Failed to start SIP client: {e}")
                phone = None

@app.route('/')
def index():
    status = "Unknown"
    if phone:
        status = str(phone._status).split('.')[-1]
    return f"SIP API is active. Current Status: {status}. Use /call?call=NUMBER"

@app.route('/call', methods=['GET', 'POST'])
def make_call():
    if request.method == 'POST' and request.is_json:
        data = request.json
    else:
        data = request.args

    destination = data.get('call') or data.get('destination')

    if not destination:
        return jsonify({"error": "Missing 'call' parameter"}), 400

    if not phone or phone._status != PhoneStatus.REGISTERED:
        current_status = str(phone._status).split('.')[-1] if phone else "None"
        logger.warning(f"Call rejected: SIP not registered (Status: {current_status})")
        return jsonify({"error": f"SIP not registered. Status: {current_status}"}), 503

    try:
        logger.info(f"Initiating call to {destination}")
        call = phone.call(destination)
        
        def monitor(target_call, dest):
            start_time = time.time()
            try:
                while target_call.state != CallState.ENDED and (time.time() - start_time) < 90:
                    if target_call.state == CallState.ANSWERED:
                        logger.info(f"Call to {dest} ANSWERED. Hanging up in 1s.")
                        time.sleep(1)
                        target_call.hangup()
                        break
                    time.sleep(0.5)
                
                if target_call.state != CallState.ENDED:
                    logger.info(f"Call to {dest} timed out. Hanging up.")
                    target_call.hangup()
            except Exception as e:
                logger.error(f"Monitor error for {dest}: {e}")

        threading.Thread(target=monitor, args=(call, destination), daemon=True).start()
        
        return jsonify({"message": f"Calling {destination}", "status": "Initiated"})

    except Exception as e:
        logger.exception("Call failed")
        return jsonify({"error": str(e)}), 500

# Start SIP registration in background immediately
threading.Thread(target=init_sip, daemon=True).start()

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)
