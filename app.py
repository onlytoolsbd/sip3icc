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
    return "SIP API is running. Use /call?call=NUMBER to make a call."

@app.route('/call', methods=['GET', 'POST'])
def make_call():
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

    try:
        p = get_phone(server, username, password)
        if p._status != PhoneStatus.REGISTERED:
            # Try to restart if failed
            if p._status == PhoneStatus.FAILED:
                p.stop()
                global phone
                phone = None
                p = get_phone(server, username, password)
            
            if p._status != PhoneStatus.REGISTERED:
                return jsonify({"error": f"SIP Registration failed: {p._status}"}), 500

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
        
        return jsonify({
            "message": f"Calling {destination}",
            "status": "Initiated",
            "auto_hangup": "Enabled"
        })

    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)
