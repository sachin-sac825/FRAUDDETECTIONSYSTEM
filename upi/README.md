# Real-Time UPI Fraud Demo

Quickly run and test the real-time fraud detection prototype.

## Quick start

1. Install dependencies (your environment may already have them):

```powershell
pip install -r requirements.txt
```

2. Start the app:

```powershell
python app.py
```

3. Open the UI: http://127.0.0.1:5000

4. Health check: http://127.0.0.1:5000/health (returns JSON)

**Optional: SHAP explainability**

- Install SHAP to enable per-transaction explanations used by the `/api/explain/<tx_id>` endpoint and UI features:

```powershell
pip install shap
```

- The app will continue to run without SHAP; explanation-related endpoints will return `no_explanation` when SHAP is not installed.

## Programmatic ingest examples

Curl (Linux/macOS):

```bash
curl -X POST http://127.0.0.1:5000/api/ingest \
  -H "Content-Type: application/json" \
  -d '{"upi_number":"demo@upi","amount":25000,"hour":23,"day":24,"month":12,"year":2025,"merchant":"Zomato","category":"Food","location":"Mumbai"}'
```

PowerShell:

```powershell
$body = '{"upi_number":"demo@upi","amount":25000,"hour":23,"day":24,"month":12,"year":2025,"merchant":"Zomato","category":"Food","location":"Mumbai"}'
Invoke-RestMethod -Uri http://127.0.0.1:5000/api/ingest -Method Post -Body $body -ContentType 'application/json'
```

## Notes
- A small `/favicon.ico` handler returns 204 to avoid noisy 404 logs during demos.
- Sanity tests are in `tests/sanity_test.py` — run them with `python tests/sanity_test.py`.

## Security & deployment notes 🔐
- Tokenization: deterministic tokens for UPIs/VPAs are generated using the `TOKEN_SALT` env var. Set a repo-specific salt in production: `export TOKEN_SALT="<strong_random_salt>"` (or set in your environment on Windows).
- DB at-rest encryption: optionally enable field-level encryption (Fernet) by setting `DB_ENCRYPTION_KEY`. A short passphrase is accepted and will be derived to a 32-byte Fernet key. Example:

```powershell
# Windows PowerShell
$env:DB_ENCRYPTION_KEY = 'my_very_secret_passphrase'
# Optionally set TOKEN_SALT
$env:TOKEN_SALT = 'change_this'
```

- If `DB_ENCRYPTION_KEY` is not set, the app will store plaintext fields (dev-friendly fallback), but you should always set it in production.
- To run the new encryption/tokenization tests:

```powershell
$env:PYTHONPATH='.'; python tests/test_encryption.py
```

## WebAuthn (FIDO2) scaffold 🛡️
- This project includes a WebAuthn scaffold that provides registration and authentication endpoints. It works in two modes:
  - Full mode (recommended): install `python-fido2` and use a browser + authenticator to register real credentials.
  - Demo mode: if `python-fido2` is not installed, endpoints return demo options and accept demo payloads for development.

- To enable full WebAuthn functionality, install the dependency:

```powershell
pip install python-fido2
```

- Routes:
  - `POST /webauthn/register/begin`  — start registration (body: `{upi: 'user@upi'}`)
  - `POST /webauthn/register/complete` — finish registration (attestation payload)
  - `POST /webauthn/authenticate/begin` — start authentication
  - `POST /webauthn/authenticate/complete` — finish authentication (assertion payload)

- To try the scaffold UI page: open `/webauthn_manage` (dev page with a "Begin registration" button).

### Running WebAuthn integration tests (requires authenticator)
- By default the WebAuthn integration tests are skipped. To run them against a real authenticator set the env var `RUN_WEBAUTHN_INTEGRATION=1` and run pytest, for example:

```powershell
# Windows PowerShell (PowerShell Core or Windows PowerShell)
$env:RUN_WEBAUTHN_INTEGRATION = '1'
$env:PYTHONPATH = '.'
python -m pytest -q tests/test_webauthn_integration.py
```

- Notes:
  - Ensure you run the tests on a machine with a platform or external security key available and a browser that can complete attestation if you plan to exercise end-to-end registration flows.
  - The tests are intentionally conservative — they check server-side options and will only run when you explicitly enable them to avoid CI and dev friction.

