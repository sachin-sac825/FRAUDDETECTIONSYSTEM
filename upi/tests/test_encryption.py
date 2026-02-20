import os
import tempfile
import sqlite3
from pprint import pprint

# ensure tests import local modules
os.environ['PYTHONPATH'] = os.environ.get('PYTHONPATH', '') + ('' if os.environ.get('PYTHONPATH') else '.')

# Set deterministic salts/keys for test
os.environ['TOKEN_SALT'] = 'test_salt'
os.environ['DB_ENCRYPTION_KEY'] = 'test_db_key'

import database
from security import tokenize_identifier


def test_tokenize_and_encrypt():
    # use a temporary DB file so tests are isolated
    tmp = tempfile.NamedTemporaryFile(delete=False)
    db_path = tmp.name
    tmp.close()

    database.init_db(db_path=db_path)

    tx = {
        'timestamp': '2025-12-27 12:00:00',
        'upi': 'alice@upi',
        'amount': 99.99,
        'merchant': 'Cafe',
        'category': 'Food',
        'location': 'City',
        'risk_score': 0.1,
        'status': 'completed',
        'indicators': ['low_amount'],
        'explanation': {'rules': ['low_amount']},
        'features': {'freq_last_hour': 2}
    }

    rid = database.save_transaction(tx)
    assert rid > 0

    # raw DB check: encrypted fields should not equal plaintext JSON
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    cur.execute('SELECT explanation, features, upi_token FROM transactions WHERE id = ?', (rid,))
    row = cur.fetchone()
    conn.close()

    raw_explanation, raw_features, raw_upi_token = row
    assert raw_explanation is not None
    assert raw_features is not None
    # Fernet ciphertexts start with 'gAAAA' when used (check it's not plaintext JSON)
    assert not raw_explanation.startswith('{')
    assert not raw_features.startswith('{')

    # Fetch via DB helper — should be decrypted
    got = database.get_transaction_by_id(rid)
    assert got is not None
    assert got['explanation'] == tx['explanation']
    assert got['features'] == tx['features']

    # Tokenization deterministic check
    expected_token = tokenize_identifier('alice@upi')
    assert got['upi_token'] == expected_token

    # vpa reputation helper roundtrip
    vpa_hash = tokenize_identifier('bob@upi')
    database.set_vpa_reputation(vpa_hash, flag_count=3, reputation_score=0.2, reasons=['test'])
    rep = database.get_vpa_reputation(vpa_hash)
    assert rep['flag_count'] == 3
    assert rep['reputation_score'] == 0.2
    assert rep['reasons'] == ['test']


if __name__ == '__main__':
    test_tokenize_and_encrypt()
    print('test_tokenize_and_encrypt: OK')
