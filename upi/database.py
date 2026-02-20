import sqlite3
import json
import os
from typing import List, Dict, Any

DB_PATH = os.path.join(os.path.dirname(__file__), 'upi.db')


def get_conn():
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def init_db(db_path: str = None):
    global DB_PATH
    if db_path:
        DB_PATH = db_path
    conn = get_conn()
    cur = conn.cursor()
    cur.execute('''
        CREATE TABLE IF NOT EXISTS transactions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT,
            upi TEXT,
            amount REAL,
            merchant TEXT,
            category TEXT,
            location TEXT,
            risk_score REAL,
            status TEXT,
            indicators TEXT
        )
    ''')
    # Ensure blocked columns exist (migration path)
    cur.execute("PRAGMA table_info(transactions)")
    cols = [r[1] for r in cur.fetchall()]
    if 'blocked' not in cols:
        cur.execute("ALTER TABLE transactions ADD COLUMN blocked INTEGER DEFAULT 0")
    if 'blocked_by' not in cols:
        cur.execute("ALTER TABLE transactions ADD COLUMN blocked_by TEXT")
    if 'blocked_timestamp' not in cols:
        cur.execute("ALTER TABLE transactions ADD COLUMN blocked_timestamp TEXT")
    if 'explanation' not in cols:
        cur.execute("ALTER TABLE transactions ADD COLUMN explanation TEXT")
    if 'features' not in cols:
        cur.execute("ALTER TABLE transactions ADD COLUMN features TEXT")
    if 'upi_token' not in cols:
        cur.execute("ALTER TABLE transactions ADD COLUMN upi_token TEXT")

    # audit log table for admin actions
    cur.execute('''
        CREATE TABLE IF NOT EXISTS audit_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT,
            action TEXT,
            actor TEXT,
            details TEXT
        )
    ''')
    # reputation table for VPAs (tokenized identifiers)
    cur.execute('''
        CREATE TABLE IF NOT EXISTS vpa_reputation (
            vpa_hash TEXT PRIMARY KEY,
            flag_count INTEGER DEFAULT 0,
            reputation_score REAL DEFAULT 1.0,
            reasons TEXT
        )
    ''')
    cur.execute('''
        CREATE TABLE IF NOT EXISTS user_profiles (
            upi TEXT PRIMARY KEY,
            profile_json TEXT
        )
    ''')
    
    # Users table for authentication
    cur.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            upi TEXT UNIQUE,
            display_name TEXT,
            password_hash TEXT,
            mfa_enabled INTEGER DEFAULT 0,
            mfa_secret TEXT,
            mfa_backup_codes TEXT,
            created_at TEXT
        )
    ''')
    # Ensure `mfa_backup_codes` and webauthn columns exist for existing DBs
    try:
        cur.execute("PRAGMA table_info(users)")
        ucols = [r[1] for r in cur.fetchall()]
        if 'mfa_backup_codes' not in ucols:
            cur.execute("ALTER TABLE users ADD COLUMN mfa_backup_codes TEXT")
        if 'webauthn_credentials' not in ucols:
            cur.execute("ALTER TABLE users ADD COLUMN webauthn_credentials TEXT")
    except Exception:
        pass
    conn.commit()
    conn.close()


def save_transaction(tx: Dict[str, Any]) -> int:
    conn = get_conn()
    cur = conn.cursor()
    indicators_json = json.dumps(tx.get('indicators', []))
    features_json = json.dumps(tx.get('features', {})) if tx.get('features') is not None else None
    # tokenized upi for privacy-preserving storage and reputation lookups
    upi_token = None
    try:
        from security import tokenize_identifier, encrypt_field
        upi_token = tokenize_identifier(tx.get('upi')) if tx.get('upi') else None
        enc_features = encrypt_field(features_json) if features_json is not None else None
        explanation_plain = json.dumps(tx.get('explanation')) if tx.get('explanation') is not None else None
        enc_explanation = encrypt_field(explanation_plain) if explanation_plain is not None else None
    except Exception:
        upi_token = None
        enc_features = features_json
        explanation_plain = json.dumps(tx.get('explanation')) if tx.get('explanation') is not None else None
        enc_explanation = explanation_plain
    cur.execute(
        '''INSERT INTO transactions (timestamp, upi, upi_token, amount, merchant, category, location, risk_score, status, indicators, blocked, blocked_by, blocked_timestamp, explanation, features)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)''',
        (tx.get('timestamp'), tx.get('upi'), upi_token, tx.get('amount'), tx.get('merchant'), tx.get('category'),
         tx.get('location'), tx.get('risk_score'), tx.get('status'), indicators_json, int(tx.get('blocked', 0)), tx.get('blocked_by'), tx.get('blocked_timestamp'), enc_explanation, enc_features)
    )
    conn.commit()
    rowid = cur.lastrowid
    conn.close()
    return rowid


def get_recent_transactions(limit: int = 20) -> List[Dict[str, Any]]:
    conn = get_conn()
    cur = conn.cursor()
    cur.execute('SELECT * FROM transactions ORDER BY id DESC LIMIT ?', (limit,))
    rows = cur.fetchall()
    conn.close()
    transactions = []
    for r in rows:
        t = dict(r)
        try:
            t['indicators'] = json.loads(t.get('indicators') or '[]')
        except Exception:
            t['indicators'] = []
        # parse explanation JSON if present (decrypt at-rest)
        try:
            from security import decrypt_field
            raw = decrypt_field(t.get('explanation')) if t.get('explanation') else None
            t['explanation'] = json.loads(raw) if raw else None
        except Exception:
            t['explanation'] = None
        # parse features JSON if present
        try:
            from security import decrypt_field
            rawf = decrypt_field(t.get('features')) if t.get('features') else None
            t['features'] = json.loads(rawf) if rawf else None
        except Exception:
            t['features'] = None
        transactions.append(t)
    transactions.reverse()  # oldest first
    return transactions


def get_all_transactions() -> List[Dict[str, Any]]:
    conn = get_conn()
    cur = conn.cursor()
    cur.execute('SELECT * FROM transactions ORDER BY id ASC')
    rows = cur.fetchall()
    conn.close()
    transactions = []
    for r in rows:
        t = dict(r)
        try:
            t['indicators'] = json.loads(t.get('indicators') or '[]')
        except Exception:
            t['indicators'] = []
        try:
            from security import decrypt_field
            raw = decrypt_field(t.get('explanation')) if t.get('explanation') else None
            t['explanation'] = json.loads(raw) if raw else None
        except Exception:
            t['explanation'] = None
        transactions.append(t)
    return transactions


def clear_transactions():
    """Delete all transactions from the DB and reset autoincrement."""
    conn = get_conn()
    cur = conn.cursor()
    cur.execute('DELETE FROM transactions')
    # Reset sqlite_sequence for AUTOINCREMENT (if present)
    try:
        cur.execute("DELETE FROM sqlite_sequence WHERE name='transactions'")
    except Exception:
        pass
    conn.commit()
    conn.close()
    return True


def save_user_profile(upi: str, profile: Dict[str, Any]):
    conn = get_conn()
    cur = conn.cursor()
    profile_json = json.dumps(profile)
    cur.execute('REPLACE INTO user_profiles (upi, profile_json) VALUES (?, ?)', (upi, profile_json))
    conn.commit()
    conn.close()


# -- User auth helpers --
def create_user(upi: str, display_name: str, password_hash: str, mfa_secret: str = None) -> int:
    conn = get_conn()
    cur = conn.cursor()
    ts = datetime_now_str()
    cur.execute('INSERT INTO users (upi, display_name, password_hash, mfa_enabled, mfa_secret, created_at) VALUES (?, ?, ?, ?, ?, ?)',
                (upi, display_name, password_hash, 1 if mfa_secret else 0, mfa_secret, ts))
    conn.commit()
    uid = cur.lastrowid
    conn.close()
    return uid


def get_user_by_upi(upi: str) -> Dict[str, Any]:
    conn = get_conn()
    cur = conn.cursor()
    cur.execute('SELECT * FROM users WHERE upi = ?', (upi,))
    row = cur.fetchone()
    conn.close()
    if not row:
        return None
    u = dict(row)
    return u


def set_mfa_for_user(upi: str, secret: str, enabled: bool = True, backup_codes: list = None) -> bool:
    conn = get_conn()
    cur = conn.cursor()
    codes_json = json.dumps(backup_codes) if backup_codes is not None else None
    cur.execute('UPDATE users SET mfa_secret = ?, mfa_enabled = ?, mfa_backup_codes = ? WHERE upi = ?', (secret, 1 if enabled else 0, codes_json, upi))
    conn.commit()
    ok = cur.rowcount > 0
    conn.close()
    return ok


def get_and_consume_backup_code(upi: str, code: str) -> bool:
    """Return True and consume (delete) the code if it exists for user."""
    conn = get_conn()
    cur = conn.cursor()
    cur.execute('SELECT mfa_backup_codes FROM users WHERE upi = ?', (upi,))
    row = cur.fetchone()
    if not row or not row[0]:
        conn.close()
        return False
    try:
        codes = json.loads(row[0])
    except Exception:
        codes = []
    if code not in codes:
        conn.close()
        return False
    # remove and update
    codes.remove(code)
    cur.execute('UPDATE users SET mfa_backup_codes = ? WHERE upi = ?', (json.dumps(codes), upi))
    conn.commit()
    conn.close()
    return True


def set_user_last_seen(upi: str, ts: str = None):
    """Set last_seen timestamp on user profile and persist."""
    profile = get_user_profile(upi) or {'transactions': []}
    profile['last_seen'] = ts or datetime_now_str()
    save_user_profile(upi, profile)
    return profile


# -- WebAuthn credential helpers --
def set_webauthn_credentials(upi: str, credentials: list) -> bool:
    """Store a list of webauthn credentials (serialized as JSON) on the user record."""
    conn = get_conn()
    cur = conn.cursor()
    try:
        cur.execute('UPDATE users SET webauthn_credentials = ? WHERE upi = ?', (json.dumps(credentials), upi))
        conn.commit()
        return cur.rowcount > 0
    finally:
        conn.close()


def get_webauthn_credentials(upi: str):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute('SELECT webauthn_credentials FROM users WHERE upi = ?', (upi,))
    row = cur.fetchone()
    conn.close()
    if not row or not row[0]:
        return []
    try:
        return json.loads(row[0])
    except Exception:
        return []


def add_webauthn_credential(upi: str, credential: dict) -> bool:
    creds = get_webauthn_credentials(upi) or []
    creds.append(credential)
    return set_webauthn_credentials(upi, creds)


def remove_webauthn_credential(upi: str, credential_id: str) -> bool:
    """Remove a credential by its `id` for the given user."""
    creds = get_webauthn_credentials(upi) or []
    new_creds = [c for c in creds if str(c.get('id')) != str(credential_id)]
    if len(new_creds) == len(creds):
        return False
    return set_webauthn_credentials(upi, new_creds)


def mark_transaction_blocked(tx_id: int, blocked_by: str = None) -> bool:
    conn = get_conn()
    cur = conn.cursor()
    ts = datetime_now_str()
    cur.execute('UPDATE transactions SET blocked = 1, blocked_by = ?, blocked_timestamp = ? WHERE id = ?', (blocked_by, ts, tx_id))
    conn.commit()
    changed = cur.rowcount > 0
    conn.close()
    return changed


def get_transaction_by_id(tx_id: int) -> Dict[str, Any]:
    conn = get_conn()
    cur = conn.cursor()
    cur.execute('SELECT * FROM transactions WHERE id = ?', (tx_id,))
    row = cur.fetchone()
    conn.close()
    if not row:
        return None
    t = dict(row)
    try:
        t['indicators'] = json.loads(t.get('indicators') or '[]')
    except Exception:
        t['indicators'] = []
    try:
        from security import decrypt_field
        raw = decrypt_field(t.get('explanation')) if t.get('explanation') else None
        t['explanation'] = json.loads(raw) if raw else None
    except Exception:
        t['explanation'] = None
    try:
        from security import decrypt_field
        rawf = decrypt_field(t.get('features')) if t.get('features') else None
        t['features'] = json.loads(rawf) if rawf else None
    except Exception:
        t['features'] = None
    return t


def datetime_now_str():
    from datetime import datetime
    return datetime.now().strftime('%Y-%m-%d %H:%M:%S')


def count_transactions_for_upi(upi: str, minutes: int = 60) -> int:
    conn = get_conn()
    cur = conn.cursor()
    # compare timestamp to current time minus minutes; use tokenized upi if present
    try:
        from security import tokenize_identifier
        upi_token = tokenize_identifier(upi)
    except Exception:
        upi_token = None
    cur.execute("SELECT COUNT(*) as cnt FROM transactions WHERE (upi = ? OR upi_token = ?) AND datetime(timestamp) > datetime('now', ?)", (upi, upi_token, f'-{minutes} minutes'))
    row = cur.fetchone()
    conn.close()
    return int(row['cnt']) if row else 0


def get_last_transaction_for_upi(upi: str) -> Dict[str, Any]:
    conn = get_conn()
    cur = conn.cursor()
    try:
        from security import tokenize_identifier
        upi_token = tokenize_identifier(upi)
    except Exception:
        upi_token = None
    cur.execute('SELECT * FROM transactions WHERE (upi = ? OR upi_token = ?) ORDER BY id DESC LIMIT 1', (upi, upi_token))
    row = cur.fetchone()
    conn.close()
    if not row:
        return None
    t = dict(row)
    try:
        t['indicators'] = json.loads(t.get('indicators') or '[]')
    except Exception:
        t['indicators'] = []
    try:
        from security import decrypt_field
        raw = decrypt_field(t.get('explanation')) if t.get('explanation') else None
        t['explanation'] = json.loads(raw) if raw else None
    except Exception:
        t['explanation'] = None
    try:
        from security import decrypt_field
        rawf = decrypt_field(t.get('features')) if t.get('features') else None
        t['features'] = json.loads(rawf) if rawf else None
    except Exception:
        t['features'] = None
    return t


def log_audit(action: str, actor: str = None, details: Dict[str, Any] = None):
    conn = get_conn()
    cur = conn.cursor()
    ts = datetime_now_str()
    cur.execute('INSERT INTO audit_log (timestamp, action, actor, details) VALUES (?, ?, ?, ?)', (ts, action, actor, json.dumps(details) if details is not None else None))
    conn.commit()
    conn.close()
    return True


# -- VPA reputation helpers --
def get_vpa_reputation(vpa_hash: str) -> Dict[str, Any]:
    """Return reputation record for a tokenized VPA (vpa_hash) or None."""
    conn = get_conn()
    cur = conn.cursor()
    cur.execute('SELECT * FROM vpa_reputation WHERE vpa_hash = ?', (vpa_hash,))
    row = cur.fetchone()
    conn.close()
    if not row:
        return None
    rec = dict(row)
    try:
        rec['reasons'] = json.loads(rec.get('reasons')) if rec.get('reasons') else []
    except Exception:
        rec['reasons'] = []
    return rec


def set_vpa_reputation(vpa_hash: str, flag_count: int = 0, reputation_score: float = 1.0, reasons: list = None) -> bool:
    """Insert or update reputation for a given tokenized VPA."""
    conn = get_conn()
    cur = conn.cursor()
    reasons_json = json.dumps(reasons) if reasons is not None else None
    cur.execute('SELECT 1 FROM vpa_reputation WHERE vpa_hash = ?', (vpa_hash,))
    exists = cur.fetchone()
    if exists:
        cur.execute('UPDATE vpa_reputation SET flag_count = ?, reputation_score = ?, reasons = ? WHERE vpa_hash = ?', (flag_count, reputation_score, reasons_json, vpa_hash))
    else:
        cur.execute('INSERT INTO vpa_reputation (vpa_hash, flag_count, reputation_score, reasons) VALUES (?, ?, ?, ?)', (vpa_hash, flag_count, reputation_score, reasons_json))
    conn.commit()
    conn.close()
    return True


def get_user_profile(upi: str) -> Dict[str, Any]:
    conn = get_conn()
    cur = conn.cursor()
    cur.execute('SELECT profile_json FROM user_profiles WHERE upi = ?', (upi,))
    row = cur.fetchone()
    conn.close()
    if not row:
        return None
    try:
        return json.loads(row['profile_json'])
    except Exception:
        return None


def get_recent_audit_logs(limit: int = 10):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute('SELECT * FROM audit_log ORDER BY id DESC LIMIT ?', (limit,))
    rows = cur.fetchall()
    conn.close()
    logs = []
    for r in rows:
        l = dict(r)
        try:
            l['details'] = json.loads(l.get('details')) if l.get('details') else None
        except Exception:
            l['details'] = None
        logs.append(l)
    return logs
