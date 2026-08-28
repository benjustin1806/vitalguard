import json
import os
import time
import joblib
import pandas as pd
from sklearn.model_selection import train_test_split
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import accuracy_score, precision_score, recall_score, f1_score, classification_report, confusion_matrix

def main():
    print("=" * 60)
    print("VITALGUARD — ML Risk Scoring Model Training")
    print("=" * 60)

    # 1. Path setup
    base_dir = os.path.dirname(os.path.abspath(__file__))
    dataset_path = os.path.join(base_dir, "data", "human_vital_signs_dataset_2024.csv")
    model_path = os.path.join(base_dir, "model.joblib")
    features_path = os.path.join(base_dir, "feature_columns.json")

    print(f"Loading dataset from: {dataset_path}")
    start_time = time.time()
    df = pd.read_csv(dataset_path)
    print(f"Dataset loaded successfully in {time.time() - start_time:.2f}s. Shape: {df.shape}")

    # 2. Select Features and Target
    feature_cols = [
        "Heart Rate",
        "Respiratory Rate",
        "Body Temperature",
        "Oxygen Saturation",
        "Systolic Blood Pressure",
        "Diastolic Blood Pressure",
        "Derived_Pulse_Pressure",
        "Derived_MAP"
    ]
    target_col = "Risk Category"

    print(f"\nFeature columns selected ({len(feature_cols)}):")
    for fc in feature_cols:
        print(f"  - {fc}")

    # Verify target column is NOT in features
    assert target_col not in feature_cols, f"CRITICAL BUG: Target column '{target_col}' is in features list!"
    print(f"\n[OK] Confirmed '{target_col}' is NOT included in feature columns.")

    X = df[feature_cols]
    y = df[target_col]

    # Check class distribution
    print("\nClass distribution in target:")
    print(y.value_counts(normalize=True).apply(lambda v: f"{v*100:.2f}%"))

    # 3. Train/Test Split
    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.20, random_state=42, stratify=y
    )
    print(f"\nTrain set: {X_train.shape[0]} samples | Test set: {X_test.shape[0]} samples")

    # 4. Train RandomForest Classifier
    print("\nTraining RandomForestClassifier (n_estimators=100, max_depth=12)...")
    model = RandomForestClassifier(
        n_estimators=100,
        max_depth=12,
        random_state=42,
        n_jobs=-1
    )
    model.fit(X_train, y_train)

    # 5. Evaluate on Test Set
    y_pred = model.predict(X_test)
    acc = accuracy_score(y_test, y_pred)
    prec = precision_score(y_test, y_pred, pos_label="High Risk")
    rec = recall_score(y_test, y_pred, pos_label="High Risk")
    f1 = f1_score(y_test, y_pred, pos_label="High Risk")

    print("\n" + "=" * 60)
    print("EVALUATION RESULTS ON TEST SET (20% Split):")
    print("=" * 60)
    print(f"  - Accuracy:  {acc * 100:.2f}%")
    print(f"  - Precision: {prec * 100:.2f}% (High Risk)")
    print(f"  - Recall:    {rec * 100:.2f}% (High Risk)")
    print(f"  - F1-Score:  {f1 * 100:.2f}% (High Risk)")
    print("\nConfusion Matrix:")
    print(confusion_matrix(y_test, y_pred, labels=["Low Risk", "High Risk"]))
    print("\nClassification Report:")
    print(classification_report(y_test, y_pred))

    # 6. Feature Importances
    importances = pd.Series(model.feature_importances_, index=feature_cols).sort_values(ascending=False)
    print("\nFeature Importances:")
    for col, imp in importances.items():
        print(f"  - {col:28s}: {imp:.4f}")

    # 7. Save Model & Feature Schema
    joblib.dump(model, model_path)
    print(f"\nModel saved to: {model_path}")

    with open(features_path, "w") as f:
        json.dump(feature_cols, f, indent=2)
    print(f"Feature columns saved to: {features_path}")

    print("\nTraining workflow completed successfully!")

if __name__ == "__main__":
    main()
