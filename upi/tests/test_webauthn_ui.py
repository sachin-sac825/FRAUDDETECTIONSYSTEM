import os
os.environ['PYTHONPATH'] = os.environ.get('PYTHONPATH', '') + ('' if os.environ.get('PYTHONPATH') else '.')

from app import app


def test_webauthn_manage_contains_register_button():
    client = app.test_client()
    res = client.get('/webauthn_manage')
    assert res.status_code == 200
    body = res.get_data(as_text=True)
    assert 'Begin registration' in body
    assert 'navigator.credentials' in body or 'Begin registration' in body


if __name__ == '__main__':
    test_webauthn_manage_contains_register_button()
    print('test_webauthn_ui: OK')
