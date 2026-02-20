from flask import Flask, request, jsonify, render_template, Response, session, redirect, url_for
import os
import pickle
import numpy as np
import pandas as pd
from datetime import datetime, timedelta
import queue
import json
import database

try:
    import analytics
    try:
        analytics.init_analytics()
        print('✓ Analytics initialized')
    except Exception as e:
        print(f'⚠️ Analytics init failed: {e}')
except Exception:
    analytics = None

app = Flask(__name__)
app.secret_key = os.environ.get('FLASK_SECRET_KEY', 'dev-secret-change-this')

# Initialize database
database.init_db()


@app.after_request
def add_no_cache_headers(response):
    # Prevent browsers from caching pages so reopening shows a fresh form/state
    response.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0'
    response.headers['Pragma'] = 'no-cache'
    response.headers['Expires'] = '0'
    return response

# Load models
models = {}
model_names = ['logistic_regression', 'decision_tree', 'random_forest', 'support_vector_machine']
for name in model_names:
    try:
        # model pickles moved to `models/` for repository cleanliness
        with open(os.path.join('models', f'{name}_model.pkl'), 'rb') as f:
            models[name] = pickle.load(f)
        print(f"✓ Loaded {name} model")
    except Exception as e:
        print(f"✗ Error loading {name}: {e}")
        models[name] = None

# Optional SHAP explainability (import lazily inside compute_shap_explanation to avoid heavy startup cost)
shap = None
shap_available = False


# Load recent transaction history from DB (persistent)

transaction_history = database.get_recent_transactions(100)

# In-memory cache of user profiles; on-demand fallback to DB
user_profiles = {}

@app.route('/')
def index():
    # expose admin token presence to client-side for convenience (only passes empty string if not set)
    admin_token = os.environ.get('CLEAR_TRANSACTIONS_TOKEN') or ''
    user = None
    try:
        user = None if 'user' not in session else session.get('user')
    except Exception:
        user = None
    return render_template('index.html', admin_token=admin_token, current_user=user)


# --- Authentication routes ---
@app.route('/register', methods=['GET', 'POST'])
def register():
    try:
        if request.method == 'GET':
            return render_template('register.html')
        upi = request.form.get('upi')
        display_name = request.form.get('display_name')
        password = request.form.get('password')
        if not upi or not password:
            return render_template('register.html', error='Missing fields')
        # check exists
        if database.get_user_by_upi(upi):
            return render_template('register.html', error='User already exists')
        # hash password
        from security import hash_password, generate_totp_secret
        pw_hash = hash_password(password)
        # create user with no mfa initially (mfa setup can be done later)
        database.create_user(upi, display_name, pw_hash, None)
        return render_template('login.html', error='Account created, please sign in')
    except Exception as e:
        return render_template('register.html', error=str(e))


@app.route('/login', methods=['GET', 'POST'])
def login():
    try:
        if request.method == 'GET':
            return render_template('login.html')
        upi = request.form.get('upi')
        password = request.form.get('password')
        if not upi or not password:
            return render_template('login.html', error='Missing credentials')
        user = database.get_user_by_upi(upi)
        if not user:
            return render_template('login.html', error='Invalid credentials')
        from security import verify_password
        if not verify_password(user.get('password_hash',''), password):
            return render_template('login.html', error='Invalid credentials')
        # Check if MFA enabled
        if user.get('mfa_enabled'):
            # set a temporary flag in session and prompt for TOTP
            session['pending_mfa_user'] = upi
            return redirect('/mfa')
        # login
        session['user'] = {'upi': user.get('upi'), 'display_name': user.get('display_name')}
        return redirect('/')
    except Exception as e:
        return render_template('login.html', error=str(e))


@app.route('/logout')
def logout():
    session.pop('user', None)
    return redirect('/')


@app.route('/mfa', methods=['GET', 'POST'])
def mfa():
    """MFA entry and verification. If user has no secret, let them setup."""
    try:
        pending = session.get('pending_mfa_user')
        if not pending:
            return redirect('/login')
        user = database.get_user_by_upi(pending)
        from security import verify_totp, generate_totp_secret, totp_uri
        if request.method == 'GET':
            if not user.get('mfa_enabled'):
                # Show setup page with QR uri
                secret = generate_totp_secret()
                session['mfa_setup_secret'] = secret
                uri = totp_uri(secret, user=pending)
                return render_template('mfa_setup.html', uri=uri, secret=secret)
            return render_template('mfa_verify.html')
        # POST - verify token or backup code
        token = request.form.get('token')
        # If they are setting up, use setup secret
        secret = session.pop('mfa_setup_secret', None) or user.get('mfa_secret')
        if not secret and not token:
            return render_template('mfa_verify.html', error='MFA not setup')

        # allow backup code usage as fallback
        from database import get_and_consume_backup_code
        if token and len(token) == 8 and get_and_consume_backup_code(pending, token):
            # backup code accepted
            session.pop('pending_mfa_user', None)
            session['user'] = {'upi': user.get('upi'), 'display_name': user.get('display_name')}
            return redirect('/')

        if not verify_totp(secret, token):
            return render_template('mfa_verify.html', error='Invalid token or backup code')
        # if we were in setup flow, save secret + generate backup codes
        if not user.get('mfa_enabled'):
            # generate backup codes
            import secrets
            codes = [secrets.token_hex(4) for _ in range(8)]
            database.set_mfa_for_user(pending, secret, enabled=True, backup_codes=codes)
            # show codes to user
            session.pop('pending_mfa_user', None)
            session['user'] = {'upi': user.get('upi'), 'display_name': user.get('display_name')}
            return render_template('mfa_backup_codes.html', codes=codes)
        # finish login
        session.pop('pending_mfa_user', None)
        session['user'] = {'upi': user.get('upi'), 'display_name': user.get('display_name')}
        return redirect('/')
    except Exception as e:
        return render_template('mfa_verify.html', error=str(e))


# -- WebAuthn routes (scaffold) --
@app.route('/webauthn/register/begin', methods=['POST'])
def webauthn_register_begin():
    try:
        payload = request.get_json() or request.form
        upi = payload.get('upi') or (session.get('user') or {}).get('upi')
        if not upi:
            return jsonify({'success': False, 'error': 'missing_upi'}), 400
        import webauthn
        res = webauthn.begin_registration(upi)
        return jsonify(res)
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/webauthn/register/complete', methods=['POST'])
def webauthn_register_complete():
    try:
        payload = request.get_json() or request.form
        upi = payload.get('upi') or (session.get('user') or {}).get('upi')
        if not upi:
            return jsonify({'success': False, 'error': 'missing_upi'}), 400
        att = payload.get('attestation') or payload
        import webauthn
        res = webauthn.complete_registration(upi, att)
        return jsonify(res)
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/webauthn/authenticate/begin', methods=['POST'])
def webauthn_auth_begin():
    try:
        payload = request.get_json() or request.form
        upi = payload.get('upi') or (session.get('user') or {}).get('upi')
        if not upi:
            return jsonify({'success': False, 'error': 'missing_upi'}), 400
        import webauthn
        res = webauthn.begin_authentication(upi)
        return jsonify(res)
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/webauthn/authenticate/complete', methods=['POST'])
def webauthn_auth_complete():
    try:
        payload = request.get_json() or request.form
        upi = payload.get('upi') or (session.get('user') or {}).get('upi')
        if not upi:
            return jsonify({'success': False, 'error': 'missing_upi'}), 400
        assertion = payload.get('assertion') or payload
        import webauthn
        res = webauthn.complete_authentication(upi, assertion)
        if res.get('success'):
            # successful auth -> set session
            session['user'] = {'upi': upi, 'display_name': upi}
        return jsonify(res)
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/favicon.ico')
def favicon():
    # Return 204 No Content to avoid noisy 404s from browsers during demos
    return Response(status=204)


@app.route('/webauthn_manage')
def webauthn_manage():
    # Simple UI page to exercise WebAuthn scaffold endpoints
    return render_template('webauthn_manage.html')


@app.route('/account')
def account():
    # user account page (requires login)
    user = session.get('user')
    if not user:
        return redirect('/login')
    upi = user.get('upi')
    # fetch webauthn credentials for the user
    creds = database.get_webauthn_credentials(upi) or []
    return render_template('account.html', current_user=user, webauthn_creds=creds)


@app.route('/webauthn/credential/delete', methods=['POST'])
def webauthn_credential_delete():
    user = session.get('user')
    if not user:
        return jsonify({'success': False, 'error': 'not_authenticated'}), 403
    payload = request.get_json() or request.form
    cred_id = payload.get('id')
    if not cred_id:
        return jsonify({'success': False, 'error': 'missing_id'}), 400
    ok = database.remove_webauthn_credential(user.get('upi'), cred_id)
    return jsonify({'success': ok})


@app.route('/health')
def health():
    return jsonify({'status': 'ok'})


@app.route('/api/explain/<int:tx_id>')
def get_explanation(tx_id):
    tx = database.get_transaction_by_id(tx_id)
    if not tx:
        return jsonify({'success': False, 'error': 'not_found'}), 404
    if not tx.get('explanation'):
        return jsonify({'success': False, 'error': 'no_explanation'}), 404
    return jsonify({'success': True, 'explanation': tx.get('explanation')})


@app.route('/api/clear_transactions', methods=['POST'])
def clear_transactions():
    """Clear all transactions from the DB and in-memory caches. Protected by CLEAR_TRANSACTIONS_TOKEN if set."""
    try:
        expected = os.environ.get('CLEAR_TRANSACTIONS_TOKEN')
        if expected:
            # check header first, then JSON body
            token = request.headers.get('X-Admin-Token')
            if not token:
                payload = request.get_json(silent=True) or {}
                token = payload.get('token')
            if token != expected:
                print('Forbidden: invalid or missing CLEAR_TRANSACTIONS_TOKEN')
                return jsonify({'success': False, 'error': 'forbidden'}), 403

        database.clear_transactions()
        # audit log the clear action
        try:
            database.log_audit('clear_transactions', actor='admin', details={'remote_addr': request.remote_addr, 'protected': bool(expected)})
        except Exception:
            pass
        # clear in-memory history
        global transaction_history, user_profiles
        transaction_history = []
        # also clear transactions field in user_profiles
        for upi, prof in list(user_profiles.items()):
            prof['transactions'] = []
            try:
                database.save_user_profile(upi, prof)
            except Exception:
                pass
        # push a stream event to notify clients
        push_event({'type': 'clear', 'message': 'All transactions cleared by operator'})
        return jsonify({'success': True})
    except Exception as e:
        print(f"Error clearing transactions: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

def analyze_fraud_indicators(upi, amount, hour, category, merchant, location):
    """Analyze multiple fraud indicators"""
    indicators = []
    fraud_score = 0
    # load profile from cache or DB
    if upi not in user_profiles:
        p = database.get_user_profile(upi)
        if p:
            user_profiles[upi] = p
        else:
            user_profiles[upi] = {'transactions': []}

    profile = user_profiles[upi]
    
    if amount > 50000:
        indicators.append({
            'name': 'Very High Amount',
            'description': f'Transaction amount (₹{amount}) is extremely high',
            'risk': 40
        })
        fraud_score += 40
    elif amount > 20000:
        indicators.append({
            'name': 'High Amount',
            'description': f'Transaction amount (₹{amount}) is significantly high',
            'risk': 25
        })
        fraud_score += 25
    
    if hour > 23 or hour < 4:
        indicators.append({
            'name': 'Late Night Transaction',
            'description': f'Transaction at {hour}:00 - unusual time',
            'risk': 20
        })
        fraud_score += 20
    elif hour > 22 or hour < 6:
        indicators.append({
            'name': 'Off-Peak Timing',
            'description': f'Transaction at {hour}:00 - outside normal hours',
            'risk': 10
        })
        fraud_score += 10
    
    merchant_history = [t.get('merchant', '') for t in profile['transactions']]
    if merchant not in merchant_history and len(merchant_history) > 0:
        indicators.append({
            'name': 'Unknown Merchant',
            'description': f'First time transaction to {merchant}',
            'risk': 15
        })
        fraud_score += 15
    
    return indicators, fraud_score


# Real-time event subscribers (for Server-Sent Events)
subscribers = []  # list of queue.Queue


def push_event(event: dict):
    payload = json.dumps(event)
    # send to all subscribers
    for q in list(subscribers):
        try:
            q.put(payload, block=False)
        except Exception:
            # subscriber likely closed; ignore
            pass


def build_feature_dataframe(amount, hour):
    # Keep feature names consistent with training script (`amount`, `time`)
    return pd.DataFrame([[amount, hour]], columns=['amount', 'time'])


def compute_shap_explanation(features_df):
    """Compute SHAP explanation for the given features using the RandomForest model (if available). Returns a dict or None."""
    # Try to import shap lazily (may be heavy); if not available, return empty explanation
    global shap, shap_available
    if shap is None:
        try:
            import shap as _shap
            shap = _shap
            shap_available = True
            print('✓ SHAP is available for explainability')
        except Exception as e:
            shap_available = False
            print(f'⚠️ SHAP import failed: {e}');
            return {'base_value': None, 'contributions': {}}

    # Try the newer high-level API first (returns consistent arrays)
    try:
        explainer = shap.Explainer(models['random_forest'], features_df)
        res = explainer(features_df)
        vals = np.asarray(res.values)
        if vals.ndim == 1:
            vals = vals.reshape(1, -1)
        contributions = {col: float(vals[0, i]) for i, col in enumerate(features_df.columns.tolist())}
        base_value = None
        try:
            bv = res.base_values
            base_arr = np.asarray(bv)
            base_value = float(base_arr.ravel()[-1])
        except Exception:
            base_value = None
        return {'base_value': base_value, 'contributions': contributions}
    except Exception as e:
        print(f"Error using shap.Explainer: {e}")
        # fallback to TreeExplainer API
        try:
            explainer = shap.TreeExplainer(models['random_forest'])
            shap_values = explainer.shap_values(features_df)
        except Exception as e:
            print(f"Error computing shap_values (fallback): {e}")
            return {'base_value': None, 'contributions': {}}

        # shap_values may be a list (per class) for classifiers
        if isinstance(shap_values, list):
            vals = shap_values[1] if len(shap_values) > 1 else shap_values[0]
        else:
            vals = shap_values

        try:
            arr = np.asarray(vals)
            # ensure 2D: samples x features
            if arr.ndim == 1:
                arr = arr.reshape(1, -1)
            contributions = {col: float(arr[0, i]) for i, col in enumerate(features_df.columns.tolist())}
        except Exception as e:
            print(f"Error parsing SHAP values into contributions (fallback): {e}")
            return {'base_value': None, 'contributions': {}}

        base_value = None
        try:
            ev = explainer.expected_value
            if isinstance(ev, (list, tuple, np.ndarray)):
                ev_arr = np.asarray(ev)
                try:
                    base_value = float(ev_arr.ravel()[-1])
                except Exception:
                    base_value = None
            else:
                base_value = float(ev)
        except Exception:
            base_value = None

        return {'base_value': base_value, 'contributions': contributions}


def process_transaction(upi_number, amount, hour, day, month, year, merchant, category, location, device_id=None):
    """Process a transaction: run models, indicators, persist, and publish event. Optional device_id for fingerprinting."""
    features_df = build_feature_dataframe(amount, hour)

    predictions = {}
    for name, model in models.items():
        if model is None:
            predictions[name] = {'prediction': 0, 'confidence': None}
            continue
        try:
            pred = model.predict(features_df)[0]
            conf = None
            if hasattr(model, 'predict_proba'):
                proba = model.predict_proba(features_df)[0]
                conf = round(max(proba) * 100, 2)
            predictions[name] = {'prediction': int(pred), 'confidence': conf}
        except Exception as e:
            print(f"Error predicting with {name}: {e}")
            predictions[name] = {'prediction': 0, 'confidence': None}

    # compute frequency features (rolling windows: 1h, 6h, 24h, 7d)
    last_1h = database.count_transactions_for_upi(upi_number, minutes=60)
    last_6h = database.count_transactions_for_upi(upi_number, minutes=6*60)
    last_24h = database.count_transactions_for_upi(upi_number, minutes=24*60)
    last_7d = database.count_transactions_for_upi(upi_number, minutes=7*24*60)

    # last transaction info
    last_tx = database.get_last_transaction_for_upi(upi_number)

    # add frequency and optional device_id to features
    features_obj = {
        'count_1h': last_1h,
        'count_6h': last_6h,
        'count_24h': last_24h,
        'count_7d': last_7d
    }
    if device_id:
        features_obj['device_id'] = device_id

    # analyze indicators (base)
    indicators, indicator_score = analyze_fraud_indicators(upi_number, amount, hour, category, merchant, location)

    # Enrich features with analytics (graph + anomaly) when available
    try:
        if 'analytics' in globals() and analytics is not None:
            extra_feats = analytics.compute_features_for_tx({'upi': upi_number, 'merchant': merchant, 'amount': amount, 'hour': hour})
            if extra_feats:
                # merge into features and consider anomaly in indicator scoring
                features_obj.update(extra_feats)
                a_score = float(extra_feats.get('anomaly_score') or 0)
                if a_score > 0.7:
                    indicators.append({'name': 'Anomalous Behavior', 'description': f'Anomaly score {a_score:.2f}', 'risk': 30})
                    indicator_score += 30
    except Exception as e:
        print(f'Analytics error: {e}')

    # location change indicator: if last tx exists and location differs within 2 hours
    if last_tx:
        try:
            # parse timestamp
            last_ts = datetime.strptime(last_tx['timestamp'], '%Y-%m-%d %H:%M:%S')
            diff_minutes = (datetime.now() - last_ts).total_seconds() / 60.0
            if last_tx.get('location') and last_tx.get('location') != location and diff_minutes < 120:
                indicators.append({'name': 'Location Changed', 'description': f'Location changed from {last_tx.get("location")} to {location} within {int(diff_minutes)} minutes', 'risk': 20})
                indicator_score += 20
            # attach last tx features for reference
            features_obj['last_location'] = last_tx.get('location')
            features_obj['minutes_since_last'] = int(diff_minutes)

            # device change indicator (if device differs from last tx's device within 2 hours)
            try:
                last_dev = (last_tx.get('features') or {}).get('device_id')
                if last_dev and device_id and last_dev != device_id and diff_minutes < 120:
                    indicators.append({'name': 'Device Changed', 'description': f'Device changed from {last_dev} to {device_id} within {int(diff_minutes)} minutes', 'risk': 15})
                    indicator_score += 15
            except Exception:
                pass
        except Exception:
            pass

    fraud_votes = sum(1 for p in predictions.values() if p['prediction'] == 1)
    model_fraud_score = 25 if fraud_votes > len(models) / 2 else 0

    fraud_score = min(100, indicator_score + model_fraud_score)

    overall_prediction = 1 if fraud_score >= 50 else 0


    transaction = {
        'id': None,
        'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        'upi': upi_number,
        'amount': amount,
        'merchant': merchant,
        'category': category,
        'location': location,
        'risk_score': fraud_score,
        'status': 'Fraud' if overall_prediction == 1 else 'Legitimate',
        'status_color': '#e74c3c' if overall_prediction == 1 else '#27ae60',
        'indicators': indicators,
        'blocked': 1 if overall_prediction == 1 else 0,
        'blocked_by': 'system' if overall_prediction == 1 else None,
        'blocked_timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S') if overall_prediction == 1 else None
    }

    # compute explanation (lazy import inside function); only require model
    explanation = None
    if models.get('random_forest') is not None:
        try:
            explanation = compute_shap_explanation(features_df)
            transaction['explanation'] = explanation
        except Exception as e:
            print(f"Error computing explanation: {e}")
            transaction['explanation'] = None
    else:
        transaction['explanation'] = None

    # attach computed features for persistence
    transaction['features'] = features_obj

    # persist
    try:
        tx_id = database.save_transaction(transaction)
        transaction['id'] = tx_id
    except Exception as e:
        print(f"Error saving transaction to DB: {e}")
    transaction_history.append(transaction)

    # audit: if system blocked the transaction, log it
    try:
        if transaction.get('blocked'):
            database.log_audit('auto_block', actor='system', details={'tx_id': transaction.get('id'), 'upi': upi_number, 'risk_score': fraud_score})
    except Exception:
        pass

    # update user profile in memory and persist
    if upi_number not in user_profiles:
        user_profiles[upi_number] = {'transactions': []}
    user_profiles[upi_number]['transactions'].append(transaction)
    try:
        database.save_user_profile(upi_number, user_profiles[upi_number])
    except Exception as e:
        print(f"Error saving user profile to DB: {e}")

    # push event to realtime clients
    push_event({'type': 'transaction', 'transaction': transaction, 'predictions': predictions, 'explanation': explanation})

    return transaction, predictions

@app.route('/predict', methods=['POST'])
def predict():
    """Real-time fraud detection endpoint with behavioral signals"""
    try:
        # Primary form fields
        amount = float(request.form.get('amount', 0))
        hour = int(request.form.get('hour', 0))
        day = int(request.form.get('day', 1))
        month = int(request.form.get('month', 1))
        year = int(request.form.get('year', 2024))
        payer_upi = request.form.get('payer_upi', 'N/A')
        payee_upi = request.form.get('payee_upi', 'N/A')
        merchant = request.form.get('merchant', 'Unknown Merchant')
        category = request.form.get('category', 'Transfer')
        location = request.form.get('location', 'Unknown')
        device_id = request.form.get('device_id', None)

        # Behavioral signals (optional)
        typing_speed = float(request.form.get('typing_speed', 0))
        backspace_ratio = float(request.form.get('backspace_ratio', 0))
        hesitation_time = float(request.form.get('hesitation_time', 0))
        paste_detected = int(request.form.get('paste_detected', 0))
        focus_changes = int(request.form.get('focus_changes', 0))

        # Use payer_upi as the primary UPI (for backward compat, also accept upi_number)
        upi_number = payer_upi if payer_upi != 'N/A' else request.form.get('upi_number', 'N/A')
        
        features_df = build_feature_dataframe(amount, hour)
        
        predictions = {}
        for name, model in models.items():
            if model is None:
                predictions[name] = {'prediction': 0, 'confidence': None}
                continue
            try:
                pred = model.predict(features_df)[0]
                conf = None
                if hasattr(model, 'predict_proba'):
                    proba = model.predict_proba(features_df)[0]
                    conf = round(max(proba) * 100, 2)
                predictions[name] = {'prediction': pred, 'confidence': conf}
            except Exception as e:
                print(f"Error predicting with {name}: {e}")
                predictions[name] = {'prediction': 0, 'confidence': None}
        
        indicators, indicator_score = analyze_fraud_indicators(upi_number, amount, hour, category, merchant, location)

        # Optional: Boost fraud score based on behavioral signals
        # High paste ratio or rapid typing with lots of backspacing can be suspicious
        if paste_detected and backspace_ratio > 0.2:
            indicators.append({'name': 'Suspicious Paste Pattern', 'description': 'Detected paste with high backspace ratio', 'risk': 10})
            indicator_score += 10
        
        if focus_changes > 5:
            indicators.append({'name': 'Multiple Focus Changes', 'description': f'Window focus changed {focus_changes} times', 'risk': 5})
            indicator_score += 5
        
        fraud_votes = sum(1 for p in predictions.values() if p['prediction'] == 1)
        model_fraud_score = 25 if fraud_votes > len(models) / 2 else 0
        
        fraud_score = min(100, indicator_score + model_fraud_score)
        
        overall_prediction = 1 if fraud_score >= 50 else 0
        prediction_text = 'Fraud Detected' if overall_prediction == 1 else 'Legitimate Transaction'
        
        # process and persist transaction via helper
        transaction, predictions = process_transaction(upi_number, amount, hour, day, month, year, merchant, category, location, device_id=device_id)

        # fetch recent 10 transactions for the UI (prefer DB)
        try:
            recent_tx = database.get_recent_transactions(10)
        except Exception:
            recent_tx = transaction_history[-10:]

        return render_template('index.html', 
                             prediction=prediction_text,
                             risk_score=fraud_score,
                             status=transaction['status'],
                             status_color=transaction['status_color'],
                             model_predictions=predictions,
                             fraud_indicators=indicators,
                             merchant=merchant,
                             category=category,
                             location=location,
                             amount=amount,
                             hour=hour,
                             payer_upi=payer_upi,
                             payee_upi=payee_upi,
                             predictions=predictions,
                             indicators=indicators,
                             transactions=recent_tx,
                             upi=upi_number)
    
    except Exception as e:
        return render_template('index.html', error=f'Error: {str(e)}')

@app.route('/api/transactions', methods=['GET'])
def get_transactions():
    """API endpoint to get recent transactions"""
    try:
        txs = database.get_recent_transactions(20)
    except Exception:
        txs = transaction_history[-20:]
    return jsonify({'transactions': txs})  # Last 20 transactions


@app.route('/api/ingest', methods=['POST'])
def api_ingest():
    """Ingest transaction via API (JSON) for real-time processing"""
    try:
        payload = request.get_json() or request.form
        amount = float(payload.get('amount', 0))
        hour = int(payload.get('hour', 0))
        day = int(payload.get('day', 1))
        month = int(payload.get('month', 1))
        year = int(payload.get('year', 2024))
        upi_number = payload.get('upi_number', 'N/A')
        merchant = payload.get('merchant', 'Unknown Merchant')
        category = payload.get('category', 'Transfer')
        location = payload.get('location', 'Unknown')
        # If Celery is configured, enqueue background task for processing
        try:
            from tasks import process_transaction_task
            task = process_transaction_task.delay({
                'upi_number': upi_number,
                'amount': amount,
                'hour': hour,
                'day': day,
                'month': month,
                'year': year,
                'merchant': merchant,
                'category': category,
                'location': location,
            })
            return jsonify({'success': True, 'deferred': True, 'task_id': task.id})
        except Exception:
            # fallback to synchronous processing
            tx, predictions = process_transaction(upi_number, amount, hour, day, month, year, merchant, category, location)
            return jsonify({'success': True, 'transaction': tx, 'predictions': predictions})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 400


@app.route('/api/heartbeat', methods=['POST'])
def api_heartbeat():
    """Update last_seen for a given UPI (payload: {upi_number: 'user@upi'})"""
    try:
        payload = request.get_json() or request.form
        upi = payload.get('upi_number')
        if not upi:
            return jsonify({'success': False, 'error': 'missing upi_number'}), 400
        profile = database.set_user_last_seen(upi)
        return jsonify({'success': True, 'profile': profile})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/user/<path:upi>', methods=['GET'])
def api_get_user(upi):
    try:
        profile = database.get_user_profile(upi)
        if not profile:
            return jsonify({'success': False, 'error': 'not found'}), 404
        return jsonify({'success': True, 'profile': profile})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/reputation/<string:vpa_hash>', methods=['GET'])
def api_reputation(vpa_hash):
    """Return a minimal reputation summary for a hashed VPA (demo deterministic fallback)."""
    try:
        # Try database lookup if available
        try:
            rep = database.get_vpa_reputation(vpa_hash)
        except Exception:
            rep = None

        if rep:
            return jsonify({'success': True, 'vpa_hash': vpa_hash, 'flag_count': rep.get('flag_count', 0), 'reputation_score': rep.get('reputation_score', 0.0), 'reasons': rep.get('reasons', [])})

        # Deterministic demo fallback using hash-derived pseudo-score
        import hashlib
        h = hashlib.sha256(vpa_hash.encode('utf-8')).hexdigest()
        val = int(h[:8], 16) % 1000
        risk_score = round((val / 1000.0), 3)
        flag_count = val % 5
        reasons = []
        if risk_score > 0.75:
            reasons = ['crowd_flagged', 'high_risk_history']
        elif risk_score > 0.4:
            reasons = ['low_reputation']

        return jsonify({'success': True, 'vpa_hash': vpa_hash, 'flag_count': flag_count, 'reputation_score': risk_score, 'reasons': reasons, 'risk_score': risk_score})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/stream')
def stream():
    def event_stream(q: queue.Queue):
        try:
            while True:
                try:
                    data = q.get(timeout=15)
                    yield f"data: {data}\n\n"
                except Exception:
                    # keep-alive comment
                    yield ': keep-alive\n\n'
        finally:
            # cleanup: remove this queue from subscribers
            try:
                subscribers.remove(q)
            except Exception:
                pass

    q = queue.Queue()
    subscribers.append(q)
    return app.response_class(event_stream(q), mimetype='text/event-stream')


@app.route('/api/block', methods=['POST'])
def api_block():
    try:
        payload = request.get_json() or request.form
        tx_id = int(payload.get('id'))
        blocked_by = payload.get('blocked_by', 'operator')
        ok = database.mark_transaction_blocked(tx_id, blocked_by=blocked_by)
        tx = database.get_transaction_by_id(tx_id) if ok else None
        if tx:
            # reflect in-memory cache
            for i, t in enumerate(transaction_history):
                if int(t.get('id') or 0) == tx_id:
                    transaction_history[i] = tx
                    break
            push_event({'type': 'blocked', 'transaction': tx})
        return jsonify({'success': ok, 'transaction': tx})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 400

@app.route('/api/stats', methods=['GET'])
def get_stats():
    """API endpoint to get fraud detection statistics"""
    # prefer authoritative DB values
    try:
        all_tx = database.get_all_transactions()
    except Exception:
        all_tx = transaction_history

    total_transactions = len(all_tx)
    fraud_count = sum(1 for t in all_tx if t['status'] == 'Fraud')
    fraud_rate = (fraud_count / total_transactions * 100) if total_transactions > 0 else 0

    # Calculate total amount at risk
    total_at_risk = sum(t['amount'] for t in all_tx if t['status'] == 'Fraud')

    # Calculate average risk score
    avg_risk = sum(t['risk_score'] for t in all_tx) / len(all_tx) if all_tx else 0
    
    return jsonify({
        'total_transactions': total_transactions,
        'fraud_detected': fraud_count,
        'fraud_rate': round(fraud_rate, 2),
        'legitimate_transactions': total_transactions - fraud_count,
        'total_amount_at_risk': round(total_at_risk, 2),
        'average_risk_score': round(avg_risk, 2),
        'money_saved': round(total_at_risk, 2),  # Amount that would have been lost
        'prevention_efficiency': round((fraud_count / total_transactions * 100) if total_transactions > 0 else 0, 2)
    })

@app.route('/api/banking-report', methods=['GET'])
def get_banking_report():
    """Generate a banking compliance report"""
    try:
        all_tx = database.get_all_transactions()
    except Exception:
        all_tx = transaction_history

    total_transactions = len(all_tx)
    fraud_count = sum(1 for t in all_tx if t['status'] == 'Fraud')

    # Group by fraud indicators
    indicator_stats = {}
    for t in all_tx:
        for indicator in t.get('indicators', []):
            name = indicator.get('name') if isinstance(indicator, dict) else str(indicator)
            if name not in indicator_stats:
                indicator_stats[name] = 0
            indicator_stats[name] += 1

    # Group by merchant
    merchant_risk = {}
    for t in all_tx:
        merchant = t.get('merchant', 'Unknown')
        if merchant not in merchant_risk:
            merchant_risk[merchant] = {'count': 0, 'fraud_count': 0, 'total_amount': 0}
        merchant_risk[merchant]['count'] += 1
        merchant_risk[merchant]['total_amount'] += t.get('amount', 0)
        if t['status'] == 'Fraud':
            merchant_risk[merchant]['fraud_count'] += 1
    
    return jsonify({
        'report_type': 'Banking Compliance Report',
        'total_transactions_analyzed': total_transactions,
        'fraud_detected': fraud_count,
        'fraud_rate_percent': round((fraud_count / total_transactions * 100) if total_transactions > 0 else 0, 2),
        'total_amount_at_risk': round(sum(t.get('amount', 0) for t in all_tx if t['status'] == 'Fraud'), 2),
        'indicator_statistics': indicator_stats,
        'merchant_risk_analysis': merchant_risk,
        'top_fraud_indicators': sorted(indicator_stats.items(), key=lambda x: x[1], reverse=True)[:5],
        'system_uptime': 'Active',
        'last_fraud_detected': all_tx[-1]['timestamp'] if all_tx and any(t['status'] == 'Fraud' for t in all_tx) else 'None',
        'compliance_status': 'COMPLIANT' if fraud_count > 0 else 'MONITORING'
    })

if __name__ == '__main__':
    print("✓ Starting UPI Fraud Detection App...")
    # run single-process for faster startup and avoid extra reloader on Windows
    app.run(debug=False, use_reloader=False)

