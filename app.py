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

def make_sip_call(dest):
    """SIP কল করার ব্যাকগ্রাউন্ড টাস্ক (অটো-রিট্রাই সহ)"""
    global phone_instance
    connected = False
    
    # প্রক্সি লিস্ট শাফেল করে নেওয়া হলো যাতে বারবার একই প্রক্সি ট্রাই না করে
    max_attempts = min(3, len(PROXIES))
    shuffled_proxies = random.sample(PROXIES, max_attempts)
    
    # --- PROXY RETRY LOOP ---
    for attempt, proxy_str in enumerate(shuffled_proxies, 1):
        try:
            ip_port, user, pw = proxy_str.split('|')
            ip, port = ip_port.split(':')
            
            log(f"=== Attempt {attempt}/{max_attempts} ===")
            log(f"Setting SOCKS5 Proxy to: {ip}:{port}")
            
            # গ্লোবাল সকেট প্রক্সি সেট করা
            socks.set_default_proxy(socks.SOCKS5, ip, int(port), True, user, pw)
            socket.socket = socks.socksocket

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
            
            if phone_instance._status == PhoneStatus.REGISTERED:
                log("Registration Successful!")
                connected = True
                break  # কানেক্ট হলে লুপ থেকে বের হয়ে যাবে
            else:
                log(f"Registration failed with status: {phone_instance._status}")
                phone_instance.stop()
                
        except Exception as e:
            log(f"Failed with proxy {ip}:{port} - Error: {str(e)}")
            if phone_instance:
                try:
                    phone_instance.stop()
                except:
                    pass
            time.sleep(1) # পরবর্তী প্রক্সি ট্রাই করার আগে ১ সেকেন্ড বিরতি

    if not connected:
        log("CRITICAL ERROR: All proxies failed or timed out.")
        log("Hint: Make sure your SOCKS5 proxies support UDP traffic (UDP Associate).")
        # প্রক্সি বাতিল করা হচ্ছে যাতে পরবর্তী কলগুলো স্টাক না হয়
        socks.set_default_proxy()
        socket.socket = socks.socksocket 
        return

    # --- CALL EXECUTION ---
    try:
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
        log(f"Error during call execution: {str(e)}")
        if phone_instance:
            try:
                phone_instance.stop()
            except:
                pass

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
