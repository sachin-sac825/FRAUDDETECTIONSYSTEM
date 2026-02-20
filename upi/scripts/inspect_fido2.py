import inspect
from fido2.client import Fido2Client
print('Fido2Client signature:', inspect.signature(Fido2Client))
print('methods:', [m for m in dir(Fido2Client) if not m.startswith('_')])
from fido2.ctap2 import Ctap2
print('Ctap2 signature:', inspect.signature(Ctap2))
print('Ctap2 members:', [m for m in dir(Ctap2) if not m.startswith('_')])
