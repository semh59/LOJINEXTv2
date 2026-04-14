import urllib.request
import urllib.error

req = urllib.request.Request('http://127.0.0.1:8105/ready')
try:
    res = urllib.request.urlopen(req)
    print("SUCCESS:", res.read().decode())
except urllib.error.HTTPError as e:
    print("HTTPERROR:", e.code, e.read().decode())
except Exception as e:
    print("ERROR:", e)
