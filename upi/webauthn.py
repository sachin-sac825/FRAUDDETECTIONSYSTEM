"""WebAuthn scaffold helpers.

This module provides a minimal, graceful WebAuthn (FIDO2) scaffold. If the
`fido2` Python package (python-fido2) is available, it will use it; otherwise
it provides no-op / demo behaviours so endpoints can be exercised in dev.
"""
import os
import json
from typing import Dict, Any, Tuple

try:
    from fido2.server import Fido2Server
    from fido2.webauthn import PublicKeyCredentialRpEntity
    from fido2.client import ClientData
    FIDO2_AVAILABLE = True
except Exception:
    FIDO2_AVAILABLE = False

from flask import session
import database

RP_ID = os.environ.get('WEB_AUTHN_RP_ID', 'localhost')
RP_NAME = os.environ.get('WEB_AUTHN_RP_NAME', 'UPI Fraud Demo')
ORIGIN = os.environ.get('WEB_AUTHN_ORIGIN', 'http://127.0.0.1:5000')

server = None
if FIDO2_AVAILABLE:
    rp = PublicKeyCredentialRpEntity(RP_ID, RP_NAME)
    server = Fido2Server(rp)


def is_supported() -> bool:
    return FIDO2_AVAILABLE


def begin_registration(upi: str) -> Dict[str, Any]:
    """Return options for client to create a credential.
    If FIDO2 not available, return a demo placeholder to keep flow working.
    """
    if not upi:
        return {'success': False, 'error': 'missing_upi'}
    if FIDO2_AVAILABLE and server:
        user = {'id': upi.encode('utf-8'), 'name': upi, 'displayName': upi}
        options, state = server.register_begin(user, user_verification='discouraged')
        # store state in session to complete later
        session['webauthn_registration_state'] = state
        # Ensure options are JSON serializable by encoding any binary fields to websafe base64
        try:
            def encode_bytes(obj):
                if isinstance(obj, dict):
                    return {k: encode_bytes(v) for k, v in obj.items()}
                if isinstance(obj, (list, tuple)):
                    return [encode_bytes(v) for v in obj]
                if isinstance(obj, (bytes, bytearray)):
                    return server.websafe_encode(obj)
                return obj
            safe_options = encode_bytes(options)
        except Exception:
            safe_options = options
        return {'success': True, 'options': safe_options}
    # Demo fallback
    demo = {'challenge': 'demo-challenge', 'rp': {'name': RP_NAME}, 'user': {'name': upi}}
    session['webauthn_registration_state'] = {'demo': True, 'challenge': demo['challenge']}
    return {'success': True, 'options': demo, 'message': 'webauthn not fully available; demo options returned'}


def complete_registration(upi: str, attestation_response: dict) -> Dict[str, Any]:
    """Verify attestation and store credential for user.
    On demo fallback, accept a well-formed payload and store as a placeholder.
    """
    if not upi:
        return {'success': False, 'error': 'missing_upi'}
    state = session.pop('webauthn_registration_state', None)
    if not state:
        return {'success': False, 'error': 'missing_state'}
    if FIDO2_AVAILABLE and server:
        try:
            # Attestation fields may be sent as websafe base64 strings from the browser; decode them if necessary
            clientData = attestation_response.get('clientDataJSON')
            attObj = attestation_response.get('attestationObject')
            if isinstance(clientData, str):
                clientData = server.websafe_decode(clientData)
            if isinstance(attObj, str):
                attObj = server.websafe_decode(attObj)
            cred = server.register_complete(state, clientData, attObj)
            # store credential descriptor and public key
            cred_dict = {'id': cred.credential_id.hex(), 'public_key': cred.public_key.encode('pem').decode('utf-8')}
            database.add_webauthn_credential(upi, cred_dict)
            return {'success': True, 'credential': cred_dict}
        except Exception as e:
            return {'success': False, 'error': str(e)}
    # Demo fallback: store raw attestation payload as placeholder
    if not isinstance(attestation_response, dict):
        return {'success': False, 'error': 'invalid_attestation'}
    cred_placeholder = {'id': attestation_response.get('id', 'demo-id'), 'raw': attestation_response}
    database.add_webauthn_credential(upi, cred_placeholder)
    return {'success': True, 'credential': cred_placeholder, 'warning': 'demo stored (python-fido2 not installed)'}


def begin_authentication(upi: str) -> Dict[str, Any]:
    creds = database.get_webauthn_credentials(upi)
    if not creds:
        return {'success': False, 'error': 'no_credentials'}
    if FIDO2_AVAILABLE and server:
        # convert to descriptors
        descriptors = [{'type': 'public-key', 'id': bytes.fromhex(c['id'])} for c in creds if 'id' in c]
        options, state = server.authenticate_begin(descriptors)
        session['webauthn_auth_state'] = state
        # encode binary fields to websafe base64 for JSON transport
        try:
            def encode_bytes(obj):
                if isinstance(obj, dict):
                    return {k: encode_bytes(v) for k, v in obj.items()}
                if isinstance(obj, (list, tuple)):
                    return [encode_bytes(v) for v in obj]
                if isinstance(obj, (bytes, bytearray)):
                    return server.websafe_encode(obj)
                return obj
            safe_options = encode_bytes(options)
        except Exception:
            safe_options = options
        return {'success': True, 'options': safe_options}
    # Demo fallback
    session['webauthn_auth_state'] = {'demo': True, 'challenge': 'demo-auth-challenge'}
    return {'success': True, 'options': {'challenge': 'demo-auth-challenge', 'allowCredentials': [{'id': c.get('id')} for c in creds]}}


def complete_authentication(upi: str, assertion: dict) -> Dict[str, Any]:
    state = session.pop('webauthn_auth_state', None)
    if not state:
        return {'success': False, 'error': 'missing_state'}
    if FIDO2_AVAILABLE and server:
        try:
            # Incoming fields are websafe-base64 strings from browser; decode as needed
            cred_id = assertion.get('credentialId')
            clientData = assertion.get('clientDataJSON')
            authData = assertion.get('authenticatorData')
            signature = assertion.get('signature')
            if isinstance(clientData, str):
                clientData = server.websafe_decode(clientData)
            if isinstance(authData, str):
                authData = server.websafe_decode(authData)
            if isinstance(signature, str):
                signature = server.websafe_decode(signature)
            # credential id might be a string id (not hex); attempt to convert
            try:
                if isinstance(cred_id, str) and all(c in '0123456789abcdef' for c in cred_id.lower()):
                    cred_bytes = bytes.fromhex(cred_id)
                else:
                    cred_bytes = cred_id
            except Exception:
                cred_bytes = cred_id
            auth_data = server.authenticate_complete(state, cred_bytes, clientData, authData, signature)
            return {'success': True, 'auth_data': auth_data}
        except Exception as e:
            return {'success': False, 'error': str(e)}
    # Demo fallback: accept any assertion with 'demo' key
    if assertion.get('demo') == 'ok' or assertion.get('credentialId'):
        return {'success': True}
    return {'success': False, 'error': 'invalid_assertion'}
