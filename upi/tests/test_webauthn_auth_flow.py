import os
os.environ['PYTHONPATH'] = os.environ.get('PYTHONPATH', '') + ('' if os.environ.get('PYTHONPATH') else '.')

import database
from app import app


def test_begin_auth_endpoint_returns_options_for_user():
    upi = 'acct@upi'
    # ensure a user and a dummy credential exist
    from security import hash_password
    try:
        database.create_user(upi, 'Tester', hash_password('pw'), None)
    except Exception:
        pass
    # ensure DB initialized (avoid transient locks) and add a dummy credential id (hex)
    database.init_db()
    import time
    for _ in range(3):
        try:
            database.add_webauthn_credential(upi, {'id': 'aabbccddeeff'})
            break
        except Exception:
            time.sleep(0.1)
    else:
        raise RuntimeError('Failed to add credential due to DB lock')

    client = app.test_client()
    res = client.post('/webauthn/authenticate/begin', json={'upi': upi})
    assert res.status_code == 200
    data = res.get_json()
    assert data.get('success') is True
    assert 'options' in data
    opts = data['options']
    # allowCredentials or challenge should be present
    assert 'challenge' in opts or 'allowCredentials' in opts


if __name__ == '__main__':
    test_begin_auth_endpoint_returns_options_for_user()
    print('test_webauthn_auth_flow OK')
