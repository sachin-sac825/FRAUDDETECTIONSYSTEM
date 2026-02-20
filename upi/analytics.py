"""Lightweight analytics: graph features + anomaly detector.

This module builds a bipartite graph between UPIs and merchants using
historical transactions and fits an IsolationForest to produce an
`anomaly_score` for incoming transactions.

Designed for demo/testing. Not intended as production-grade pipeline.
"""
from typing import Dict, Any
import numpy as np
try:
    import networkx as nx
except Exception:
    nx = None
from sklearn.ensemble import IsolationForest
import database

# module-level state
G = None
if_model = None
_score_min = None
_score_max = None


def init_analytics(recalculate: bool = False):
    """Build graph from DB and fit an IsolationForest on simple numeric features."""
    global G, if_model, _score_min, _score_max
    if nx is None:
        print('analytics: networkx not available; skipping graph analytics')
        return

    txs = database.get_all_transactions()
    G = nx.Graph()

    rows = []
    for t in txs:
        upi = f"u:{t.get('upi')}"
        merchant = f"m:{t.get('merchant') or 'unknown'}"
        G.add_node(upi, type='upi')
        G.add_node(merchant, type='merchant')
        G.add_edge(upi, merchant)
        # feature row: amount, time (if available in features or timestamp), upi_degree, merchant_degree
        amount = float(t.get('amount') or 0)
        time_val = 0
        try:
            # prefer features.time if present
            feats = t.get('features') or {}
            time_val = float(feats.get('time') or 0)
        except Exception:
            time_val = 0
        rows.append((amount, time_val, upi, merchant))

    # build numeric matrix
    X = []
    for amount, time_val, upi, merchant in rows:
        upi_deg = G.degree(upi) if G.has_node(upi) else 0
        m_deg = G.degree(merchant) if G.has_node(merchant) else 0
        X.append([amount, time_val, upi_deg, m_deg])

    if len(X) < 5:
        # not enough data to fit a model
        if_model = None
        _score_min = None
        _score_max = None
        return

    X = np.array(X)
    if_model = IsolationForest(contamination=0.05, random_state=42)
    try:
        if_model.fit(X)
        # compute decision function scores on training set to record min/max
        scores = if_model.decision_function(X)  # higher means more normal
        # we'll map anomaly_score = 1 - normalized(decision_function)
        _score_min = float(scores.min())
        _score_max = float(scores.max())
        print('analytics: IsolationForest trained on', X.shape[0], 'rows')
    except Exception as e:
        print('analytics: isolation forest training failed:', e)
        if_model = None
        _score_min = None
        _score_max = None


def compute_features_for_tx(tx: Dict[str, Any]) -> Dict[str, Any]:
    """Return extra features for a single transaction.

    Returns dict keys: `graph_upi_degree`, `graph_merchant_degree`, `anomaly_score` (0-1)
    """
    global G, if_model, _score_min, _score_max
    out = {}
    if nx is None:
        return out

    if G is None:
        # try to init once
        try:
            init_analytics()
        except Exception:
            return out

    upi = f"u:{tx.get('upi')}"
    merchant = f"m:{tx.get('merchant') or 'unknown'}"
    upi_deg = G.degree(upi) if G and G.has_node(upi) else 0
    m_deg = G.degree(merchant) if G and G.has_node(merchant) else 0
    out['graph_upi_degree'] = int(upi_deg)
    out['graph_merchant_degree'] = int(m_deg)

    # numeric vector for anomaly model
    amount = float(tx.get('amount') or 0)
    time_val = float(tx.get('hour') or 0)
    vec = np.array([[amount, time_val, upi_deg, m_deg]])

    if if_model is not None:
        try:
            # decision_function: higher = normal; we invert and normalize
            raw = float(if_model.decision_function(vec)[0])
            if _score_min is not None and _score_max is not None and _score_max - _score_min > 0:
                norm = (raw - _score_min) / (_score_max - _score_min)
            else:
                norm = 0.5
            anomaly_score = max(0.0, min(1.0, 1.0 - norm))
            out['anomaly_score'] = float(anomaly_score)
        except Exception:
            out['anomaly_score'] = 0.0
    else:
        out['anomaly_score'] = 0.0

    return out
