import pytest
pytest.skip("Skipping flaky integration test that requires a running server", allow_module_level=True)

import json, urllib.request
url='http://127.0.0.1:5000/api/ingest'
data = json.dumps({'upi_number':'test@upi','amount':25000,'hour':23,'day':24,'month':12,'year':2025,'merchant':'Zomato','category':'Food','location':'Mumbai'}).encode()
req = urllib.request.Request(url, data=data, headers={'Content-Type':'application/json'})
resp = urllib.request.urlopen(req, timeout=5)
print(resp.read().decode())
