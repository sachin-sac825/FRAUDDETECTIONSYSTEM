import os
os.environ['TOKEN_SALT'] = 'test_salt'
# optional: set DB_ENCRYPTION_KEY to test encryption
os.environ['DB_ENCRYPTION_KEY'] = 'test_db_key'
import database
from security import tokenize_identifier, encrypt_field, decrypt_field
print('DB:', database.DB_PATH)
database.init_db()
# save a transaction
tx = {
    'timestamp': '2025-01-01 12:00:00',
    'upi': 'alice@upi',
    'amount': 123.45,
    'merchant': 'CoffeeShop',
    'category': 'Food',
    'location': 'City',
    'risk_score': 0.2,
    'status': 'completed',
    'indicators': ['low_amount'],
    'explanation': {'rules': ['low_amount']},
    'features': {'freq_last_hour': 2}
}
rowid = database.save_transaction(tx)
print('saved row id', rowid)
# retrieve
last = database.get_last_transaction_for_upi('alice@upi')
print('last transaction:', last)
# reputation test
vpa_hash = tokenize_identifier('bob@upi')
print('vpa_hash:', vpa_hash)
database.set_vpa_reputation(vpa_hash, flag_count=2, reputation_score=0.3, reasons=['suspicious'])
print('reputation:', database.get_vpa_reputation(vpa_hash))
