import os
import time
import threading
import logging
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

def start_sip_client():
    global phone
    with phone_lock:
        try:
            if phone:
                logger.info("Stopping existing SIP client...")
                phone.stop()
        except:
            pass
        
        logger.info(f"Starting SIP for {SIP_USER}...")
        phone = VoIPPhone(SIP_SERVER, 5060, SIP_USER, SIP_PASS, sipPort=0)
        phone.start()

def get_current_status():
    if phone is None: return "NONE"
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

    # Ensure phone is at least initializing
    if phone is None or phone._status in [PhoneStatus.FAILED, PhoneStatus.INACTIVE]:
        threading.Thread(target=start_sip_client, daemon=True).start()
        time.sleep(1)

    # ASYNCHRONOUS CALL INITIATION
    # We move the blocking phone.call() to a background thread to prevent Gunicorn timeout
    def background_call_task(target_dest):
        try:
            logger.info(f"Background thread: Starting call sequence to {target_dest}")
            
            # Wait up to 15 seconds for registration in the background
            for _ in range(10):
                if phone and phone._status == PhoneStatus.REGISTERED:
                    break
                time.sleep(1.5)
            
            logger.info(f"Background thread: Proceeding with call (Status: {get_current_status()})")
            call = phone.call(target_dest)
            
            # Monitor the call
            start_monitor = time.time()
            while call.state != CallState.ENDED and (time.time() - start_monitor) < 90:
                if call.state == CallState.ANSWERED:
                    logger.info(f"Call {target_dest} Answered! Hanging up in 1s.")
                    time.sleep(1)
                    call.hangup()
                    break
                time.sleep(0.5)
            
            try: call.hangup()
            except: pass
            logger.info(f"Background thread: Call to {target_dest} finished.")
            
        except Exception as e:
            logger.error(f"Background call error for {target_dest}: {e}")

    # Launch the call task in the background and return immediately
    threading.Thread(target=background_call_task, args=(dest,), daemon=True).start()

    return jsonify({
        "message": f"Call to {dest} has been queued",
        "sip_status": get_current_status(),
        "instruction": "The call will be attempted in the background. Check Render logs for progress."
    })

# Start SIP on boot
threading.Thread(target=start_sip_client, daemon=True).start()

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)
