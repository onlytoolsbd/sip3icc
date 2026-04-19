import os
import time
import threading
import logging
from flask import Flask, request, jsonify
from pyVoIP.VoIP import VoIPPhone, CallState, PhoneStatus

# Configure logging to see output in Render console
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)

# SIP Globals
phone = None
phone_lock = threading.Lock()

def get_phone(server, user, password):
    global phone
    with phone_lock:
        if phone is None:
            logger.info(f"Initializing SIP Phone for {user}@{server}")
            # Correct parameter for source port in pyVoIP is sipPort
            # Setting it to 0 should let the OS pick a random port
            phone = VoIPPhone(server, 5060, user, password, sipPort=0)
            phone.start()
            
            # Wait for registration
            logger.info("Waiting for registration...")
            for i in range(15):
                if phone._status == PhoneStatus.REGISTERED:
                    logger.info("SIP Registered successfully.")
                    break
                if phone._status == PhoneStatus.FAILED:
                    logger.error("SIP Registration failed immediately.")
                    break
                time.sleep(1)
        return phone

@app.route('/')
def index():
    return "SIP API is running. Use /call?call=NUMBER to make a call."

@app.route('/call', methods=['GET', 'POST'])
def make_call():
    try:
        # Try to get parameters from URL (GET) or JSON (POST)
        if request.method == 'POST' and request.is_json:
            data = request.json
        else:
            data = request.args

        server = data.get('server', 'sip.icctalk.com')
        username = data.get('username', '09639187791')
        password = data.get('password', 'okabye')
        destination = data.get('call') or data.get('destination')

        if not destination:
            return jsonify({"error": "Destination number is required. Use ?call=NUMBER"}), 400

        logger.info(f"Request to call {destination}")
        
        p = get_phone(server, username, password)
        
        if p._status != PhoneStatus.REGISTERED:
            status_str = str(p._status).split('.')[-1]
            # If failed, reset for next attempt
            if p._status == PhoneStatus.FAILED:
                with phone_lock:
                    p.stop()
                    global phone
                    phone = None
            return jsonify({"error": f"SIP Registration status: {status_str}"}), 500

        logger.info(f"Initiating call to {destination}")
        call = p.call(destination)
        
        # Background monitor for auto-hangup
        def monitor(target_call, dest):
            logger.info(f"Monitor started for call to {dest}")
            start_time = time.time()
            try:
                # Max 60 seconds monitor
                while target_call.state != CallState.ENDED and (time.time() - start_time) < 60:
                    if target_call.state == CallState.ANSWERED:
                        logger.info(f"Call to {dest} ANSWERED. Hanging up in 1s...")
                        time.sleep(1)
                        target_call.hangup()
                        break
                    time.sleep(0.5)
                
                if target_call.state != CallState.ENDED:
                    logger.info(f"Call to {dest} timed out after 60s. Hanging up.")
                    target_call.hangup()
            except Exception as e:
                logger.error(f"Monitor error: {e}")

        threading.Thread(target=monitor, args=(call, destination), daemon=True).start()
        
        return jsonify({
            "message": f"Calling {destination}",
            "status": "Initiated",
            "sip_status": "REGISTERED"
        })

    except Exception as e:
        logger.exception("Unexpected error during /call")
        return jsonify({"error": str(e)}), 500

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)
