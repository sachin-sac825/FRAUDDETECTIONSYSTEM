import os
os.environ['PYTHONPATH'] = os.environ.get('PYTHONPATH', '') + ('' if os.environ.get('PYTHONPATH') else '.')

import webauthn
from app import app


def test_webauthn_module_available():
    # Module should import and expose is_supported()
    assert hasattr(webauthn, 'is_supported')
    assert callable(webauthn.is_supported)


def test_begin_registration_demo_endpoint():
    # Use Flask test client to exercise the route (ensures session context exists)
    client = app.test_client()
    res = client.post('/webauthn/register/begin', json={'upi': 'tester@upi'})
    assert res.status_code == 200
    data = res.get_json()
    assert data.get('success') is True
    assert 'options' in data


if __name__ == '__main__':
    test_webauthn_module_available()
    test_begin_registration_demo_endpoint()
    print('webauthn scaffold tests OK')
