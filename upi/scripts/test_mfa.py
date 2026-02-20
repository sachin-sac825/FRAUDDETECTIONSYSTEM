import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from security import generate_totp_secret, totp_uri, verify_totp, hash_password, verify_password
import database, json
# create test user
upi='mfa_test@upi'
if database.get_user_by_upi(upi):
    print('user exists')
else:
    pw = 'SafePass123'
    ph = hash_password(pw)
    uid = database.create_user(upi, 'MFA Test', ph)
    print('created user id', uid)
# generate secret and backup codes
secret = generate_totp_secret()
import secrets
codes = [secrets.token_hex(4) for _ in range(8)]
ok = database.set_mfa_for_user(upi, secret, enabled=True, backup_codes=codes)
print('set mfa ok', ok)
print('backup codes:', codes)
# verify totp immediate (may or may not be valid depending on time)
from time import sleep
from pyotp import TOTP
totp = TOTP(secret)
print('current token', totp.now())
print('verify totp', verify_totp(secret, totp.now()))
# consume a backup code
code = codes[0]
print('consume code before', database.get_and_consume_backup_code(upi, code))
print('consume same code again', database.get_and_consume_backup_code(upi, code))