import os
import time
import threading
from flask import Flask, request, jsonify
from pyVoIP.VoIP import VoIPPhone, CallState, PhoneStatus

app = Flask(__name__)

# SIP Globals
phone = None

def get_phone(server, user, password):
    global phone
    if phone is None:
        phone = VoIPPhone(server, 5060, user, password)
        phone.start()
        # Wait for registration
        for _ in range(10):
            if phone._status == PhoneStatus.REGISTERED:
                break
            time.sleep(1)
    return phone

@app.route('/')
def index():
    return "SIP API is running. Use /call to make a call."

@app.route('/call', methods=['POST'])
def make_call():
    data = request.json
    server = data.get('server', 'sip.icctalk.com')
    username = data.get('username', '09639187791')
    password = data.get('password', 'okabye')
    destination = data.get('destination')

    if not destination:
        return jsonify({"error": "Destination number is required"}), 400

    try:
        p = get_phone(server, username, password)
        if p._status != PhoneStatus.REGISTERED:
            return jsonify({"error": "SIP Registration failed", "status": str(p._status)}), 500

        call = p.call(destination)
        
        # Background monitor for auto-hangup
        def monitor():
            time.sleep(1)
            while call.state != CallState.ENDED:
                if call.state == CallState.ANSWERED:
                    time.sleep(1)
                    call.hangup()
                    break
                time.sleep(0.5)

        threading.Thread(target=monitor, daemon=True).start()
        
        return jsonify({"message": f"Calling {destination}", "status": "Initiated"})

    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == '__main__':
    # Use environment variable for port (Render requirement)
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)
