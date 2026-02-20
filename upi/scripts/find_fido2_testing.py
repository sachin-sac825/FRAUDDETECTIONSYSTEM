import fido2
from fido2 import ctap2
members = [m for m in dir(ctap2) if not m.startswith('_')]
print('ctap2 candidates:', [m for m in members if 'Fake' in m or 'Virtual' in m or 'Test' in m or 'Fake' in m])
for name in dir(ctap2):
    if 'fake' in name.lower() or 'virtual' in name.lower() or 'test' in name.lower():
        print('ctap2 match:', name)
