import pandas as pd
from sklearn.model_selection import train_test_split
from sklearn.linear_model import LogisticRegression
from sklearn.tree import DecisionTreeClassifier
from sklearn.ensemble import RandomForestClassifier
from sklearn.svm import SVC
import pickle

# Load dataset
data = pd.read_csv('upi_fraud_dataset.csv')

# Assume features are 'amount' and 'time', target is 'is_fraud'
X = data[['amount', 'time']]
y = data['is_fraud']

# Split data
X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42)

# Train models
models = {
    'logistic_regression': LogisticRegression(),
    'decision_tree': DecisionTreeClassifier(),
    'random_forest': RandomForestClassifier(),
    'support_vector_machine': SVC()
}

for name, model in models.items():
    model.fit(X_train, y_train)
    with open(f'{name}_model.pkl', 'wb') as f:
        pickle.dump(model, f)

print("Models trained and saved.")
