import sys
import os

# Render.com এ লগগুলো যেন সাথে সাথে দেখা যায়, তাই output আনবাফার (unbuffered) করা হলো
os.environ['PYTHONUNBUFFERED'] = '1'

try:
    print("Initializing application and loading modules...", flush=True)
    import time
    import socket
    import socks
    import random
    import threading
    from flask import Flask, request, jsonify
    from pyVoIP.VoIP import VoIPPhone, CallState, PhoneStatus
    from datetime import datetime
    print("All modules loaded successfully!", flush=True)
except Exception as e:
    print(f"\nCRITICAL STARTUP ERROR: {e}", flush=True)
    if "audioop" in str(e).lower():
        print("=========================================================", flush=True)
        print(" URGENT FIX NEEDED FOR RENDER.COM", flush=True)
        print(" Python 3.13+ has removed the 'audioop' module.", flush=True)
        print(" 'pyVoIP' requires this module to process audio.", flush=True)
        print(" ", flush=True)
        print(" SOLUTION: Go to Render Dashboard -> Environment tab", flush=True)
        print(" Add a new Environment Variable:", flush=True)
        print(" Key   : PYTHON_VERSION", flush=True)
        print(" Value : 3.11.9", flush=True)
        print("=========================================================\n", flush=True)
    sys.exit(1)

app = Flask(__name__)

# আপনার দেওয়া SOCKS5 প্রক্সি লিস্ট
PROXIES = [
    "203.95.220.218:1080|w8t|w8t",
    "103.135.252.26:1080|w8t|w8t",
    "103.151.169.187:1080|w8t|w8t",
    "103.84.38.42:1080|w8t|w8t"
]

phone_instance = None

def log(msg):
    timestamp = datetime.now().strftime("%H:%M:%S")
    print(f"[{timestamp}] {msg}", flush=True)

def apply_random_proxy():
    """লিস্ট থেকে র্যান্ডম প্রক্সি নিয়ে কানেকশন সেটআপ করে"""
    try:
        proxy_str = random.choice(PROXIES)
        ip_port, user, pw = proxy_str.split('|')
        ip, port = ip_port.split(':')
        
        # গ্লোবাল সকেট প্রক্সি সেট করা
        socks.set_default_proxy(socks.SOCKS5, ip, int(port), True, user, pw)
        socket.socket = socks.socksocket
        log(f"Selected SOCKS5 Proxy: {ip}:{port}")
    except Exception as e:
        log(f"Failed to set Proxy: {str(e)}")

def make_sip_call(dest):
    """SIP কল করার ব্যাকগ্রাউন্ড টাস্ক"""
    global phone_instance
    try:
        apply_random_proxy()
        
        if phone_instance:
            try:
                phone_instance.stop()
            except:
                pass
        
        log("Registering to SIP Server...")
        phone_instance = VoIPPhone("sip.icctalk.com", 5060, "09639187791", "okabye")
        phone_instance.start()
        
        # রেজিস্ট্রেশনের জন্য অপেক্ষা
        time.sleep(2)
        
        if phone_instance._status != PhoneStatus.REGISTERED:
            log("Failed to register SIP.")
            return
        
        log(f"Successfully registered. Calling: {dest}")
        call = phone_instance.call(dest)
        
        last_state = None
        while call and call.state != CallState.ENDED:
            state = call.state
            state_str = str(state).split('.')[-1]
            
            if state_str != last_state:
                log(f"Call State: {state_str}")
                last_state = state_str
                
                # --- AUTO HANGUP LOGIC ---
                if state == CallState.ANSWERED:
                    log("Call received! Auto-hanging up in 0.5s...")
                    time.sleep(0.5)
                    call.hangup()
                    break
            
            time.sleep(0.5)
            
        log("Call Process Ended.")
        phone_instance.stop()
        
    except Exception as e:
        log(f"Error during call: {str(e)}")

@app.route('/')
def index():
    dest = request.args.get('call')
    
    if not dest:
        return jsonify({
            "status": "online",
            "message": "Render API is running. Use /?call=NUMBER to make a call."
        })
        
    # 'jan' প্যারামিটার পেলে আপনার স্পেশাল নাম্বারে রিডাইরেক্ট করবে
    if dest.lower() == "jan":
        dest = "+8801858687390"
        
    # Render-এ HTTP রিকোয়েস্ট যেন টাইমআউট না হয়, তাই কলটি ব্যাকগ্রাউন্ড থ্রেডে চালানো হচ্ছে
    threading.Thread(target=make_sip_call, args=(dest,), daemon=True).start()
    
    return jsonify({
        "status": "processing",
        "message": f"Initiating call to {dest} via proxy in the background."
    })

if __name__ == '__main__':
    # Render.com স্বয়ংক্রিয়ভাবে PORT এনভায়রনমেন্ট ভ্যারিয়েবল দেয়
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
