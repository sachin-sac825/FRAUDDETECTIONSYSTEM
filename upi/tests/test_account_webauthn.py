import os
os.environ['PYTHONPATH'] = os.environ.get('PYTHONPATH', '') + ('' if os.environ.get('PYTHONPATH') else '.')

import database
from app import app
import pytest


def setup_test_user(upi='acct@upi'):
    # create a test user (password hash not important for this test)
    pw = 'testpw'
    from security import hash_password
    try:
        database.create_user(upi, 'Tester', hash_password(pw), None)
    except Exception:
        # user may already exist
        pass


def test_account_shows_credentials_and_removal():
    upi = 'acct@upi'
    setup_test_user(upi)
    # Add a dummy credential
    cred = {'id': 'cred-1234', 'raw': {'demo': True}}
    database.add_webauthn_credential(upi, cred)

    client = app.test_client()
    # set session user
    with client.session_transaction() as sess:
        sess['user'] = {'upi': upi, 'display_name': 'Tester'}

    # Access account page
    res = client.get('/account')
    assert res.status_code == 200
    body = res.get_data(as_text=True)
    assert 'cred-1234' in body

    # Remove credential
    res2 = client.post('/webauthn/credential/delete', json={'id': 'cred-1234'})
    assert res2.status_code == 200
    data = res2.get_json()
    assert data.get('success') is True

    # Verify removed from DB
    creds = database.get_webauthn_credentials(upi)
    assert all(c.get('id') != 'cred-1234' for c in creds)


if __name__ == '__main__':
    test_account_shows_credentials_and_removal()
    print('test_account_webauthn: OK')
