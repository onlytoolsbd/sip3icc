import os
import pyVoIP
import re

# Dynamically find the path to pyVoIP's SIP.py
file_path = os.path.join(os.path.dirname(pyVoIP.__file__), "SIP.py")
print(f"Targeting: {file_path}")

if not os.path.exists(file_path):
    print(f"Error: Could not find SIP.py at {file_path}")
    exit(1)

with open(file_path, "r", encoding="utf-8") as f:
    content = f.read()

# 1. Patch header normalization (previous fix)
old_block_headers = """        for x in headers_raw:
            i = str(x, "utf8").split(": ")
            if i[0] == "Via":
                headers["Via"].append(i[1])
            if i[0] not in headers.keys():
                headers[i[0]] = i[1]"""

new_block_headers = """        for x in headers_raw:
            try:
                line = str(x, "utf8")
                if ": " in line:
                    key, val = line.split(": ", 1)
                elif ":" in line:
                    key, val = line.split(":", 1)
                else:
                    continue
                
                # Normalize common headers for pyVoIP
                norm_key = key.lower()
                if norm_key == "call-id" or norm_key == "i":
                    key = "Call-ID"
                elif norm_key == "via" or norm_key == "v":
                    key = "Via"
                elif norm_key == "from" or norm_key == "f":
                    key = "From"
                elif norm_key == "to" or norm_key == "t":
                    key = "To"
                elif norm_key == "cseq":
                    key = "CSeq"
                elif norm_key == "www-authenticate":
                    key = "WWW-Authenticate"
                elif norm_key == "authorization":
                    key = "Authorization"
                elif norm_key == "content-length" or norm_key == "l":
                    key = "Content-Length"
                elif norm_key == "content-type" or norm_key == "c":
                    key = "Content-Type"
                elif norm_key == "contact" or norm_key == "m":
                    key = "Contact"
                
                if key == "Via":
                    headers["Via"].append(val)
                elif key not in headers:
                    headers[key] = val
            except Exception:
                continue"""

# 2. Patch socket creation to use TCP instead of UDP (better for SOCKS5)
# Note: This is an experimental patch to help with SOCKS5 reliability
old_block_socket = "self.s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)"
# Actually, pyVoIP doesn't handle TCP connect() logic easily, 
# so instead of forcing TCP which requires deep rewrite, 
# we'll keep UDP but improve the monkeypatch in app.py.
# However, I'll still apply the header patch.

if old_block_headers in content:
    content = content.replace(old_block_headers, new_block_headers)
    print("Header patch applied.")
else:
    pattern = re.escape(old_block_headers).replace(r'\ ', r'\s+')
    if re.search(pattern, content):
        content = re.sub(pattern, new_block_headers, content)
        print("Header patch applied using regex.")
    else:
        print("Header block already patched or not found.")

with open(file_path, "w", encoding="utf-8") as f:
    f.write(content)
