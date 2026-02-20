"""create_models.py

Train small demo models from `upi_fraud_dataset.csv` and write pickles into `models/`.

Usage:
    python create_models.py

This script is intended for local testing only (not production).
"""

import os
import pickle
import pandas as pd
from sklearn.model_selection import train_test_split
from sklearn.linear_model import LogisticRegression
from sklearn.tree import DecisionTreeClassifier
from sklearn.ensemble import RandomForestClassifier
from sklearn.svm import SVC
from sklearn.preprocessing import StandardScaler
from sklearn.pipeline import make_pipeline
from sklearn.metrics import accuracy_score

DATA = 'upi_fraud_dataset.csv'
OUT_DIR = 'models'

os.makedirs(OUT_DIR, exist_ok=True)

if not os.path.exists(DATA):
    raise SystemExit(f"Dataset not found: {DATA}. Please ensure `{DATA}` exists in the project root.")

print('Loading dataset...')
df = pd.read_csv(DATA)
if 'amount' not in df.columns or 'time' not in df.columns or 'is_fraud' not in df.columns:
    raise SystemExit('Dataset missing required columns: amount, time, is_fraud')

X = df[['amount', 'time']]
y = df['is_fraud']

X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42)

models = {
    'logistic_regression': LogisticRegression(max_iter=2000),
    'decision_tree': DecisionTreeClassifier(),
    'random_forest': RandomForestClassifier(n_estimators=50, random_state=42),
    'support_vector_machine': make_pipeline(StandardScaler(), SVC(probability=True))
}

for name, model in models.items():
    print(f'Training {name}...')
    model.fit(X_train, y_train)
    preds = model.predict(X_test)
    acc = accuracy_score(y_test, preds)
    out_path = os.path.join(OUT_DIR, f'{name}_model.pkl')
    with open(out_path, 'wb') as f:
        pickle.dump(model, f)
    print(f'✓ Saved {name} -> {out_path}  (test acc: {acc:.3f})')

print('\nAll demo models saved. You can now run `python app.py` to start the app.')