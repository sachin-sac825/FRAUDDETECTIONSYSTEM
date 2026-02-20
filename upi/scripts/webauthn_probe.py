# Probe available fido2 testing helpers
import inspect
import fido2
from fido2 import ctap2, client, server, cbor

print('fido2 version:', fido2.__version__)
print('ctap2 members:', [m for m in dir(ctap2) if not m.startswith('_')])
print('client members:', [m for m in dir(client) if not m.startswith('_')])
print('server members:', [m for m in dir(server) if not m.startswith('_')])
print('cbor members:', [m for m in dir(cbor) if not m.startswith('_')])
