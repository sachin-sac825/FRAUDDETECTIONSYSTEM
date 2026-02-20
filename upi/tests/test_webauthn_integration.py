import os
import pytest
from app import app
import webauthn

skip_integration = os.environ.get('RUN_WEBAUTHN_INTEGRATION') != '1'


@pytest.mark.skipif(skip_integration, reason="Integration tests for WebAuthn skipped (set RUN_WEBAUTHN_INTEGRATION=1 to run)")
def test_webauthn_begin_and_options():
    """Call the registration begin endpoint and verify options are returned.

    This test is intentionally skipped by default; to run it, set the environment
    variable `RUN_WEBAUTHN_INTEGRATION=1` and perform the test on a machine with
    a real WebAuthn authenticator.
    """
    client = app.test_client()
    res = client.post('/webauthn/register/begin', json={'upi': 'integration@upi'})
    assert res.status_code == 200
    data = res.get_json()
    assert data.get('success') is True
    assert 'options' in data
    options = data['options']
    assert 'challenge' in options


if __name__ == '__main__':
    # convenience entrypoint
    pytest.main([__file__])
