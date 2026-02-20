# tests for reputation endpoint
import hashlib

from app import app


def sha256hex_py(s: str) -> str:
    return hashlib.sha256(s.strip().lower().encode('utf-8')).hexdigest()


def test_reputation_endpoint():
    client = app.test_client()
    sample_vpa = 'recipient@example'
    h = sha256hex_py(sample_vpa)
    resp = client.get(f'/api/reputation/{h}')
    assert resp.status_code == 200
    data = resp.get_json()
    assert data.get('success') is True
    assert 'reputation_score' in data or 'risk_score' in data
