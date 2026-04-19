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

old_block = """        for x in headers_raw:
            i = str(x, "utf8").split(": ")
            if i[0] == "Via":
                headers["Via"].append(i[1])
            if i[0] not in headers.keys():
                headers[i[0]] = i[1]"""

new_block = """        for x in headers_raw:
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

if old_block in content:
    new_content = content.replace(old_block, new_block)
    with open(file_path, "w", encoding="utf-8") as f:
        f.write(new_content)
    print("Patch applied successfully.")
else:
    # Try regex if exact match fails
    pattern = re.escape(old_block).replace(r'\ ', r'\s+')
    if re.search(pattern, content):
        new_content = re.sub(pattern, new_block, content)
        with open(file_path, "w", encoding="utf-8") as f:
            f.write(new_content)
        print("Patch applied successfully using regex.")
    else:
        print("Could not find the block to patch. It might already be patched.")
