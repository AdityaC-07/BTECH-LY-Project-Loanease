import os
import json
import urllib.request
import pandas as pd
import numpy as np
import joblib
from datetime import datetime
from pathlib import Path

from sklearn.model_selection import train_test_split, RandomizedSearchCV, cross_val_score
from sklearn.preprocessing import StandardScaler, OneHotEncoder, LabelEncoder
from sklearn.compose import ColumnTransformer
from sklearn.pipeline import Pipeline
from sklearn.impute import SimpleImputer
from sklearn.metrics import accuracy_score, precision_score, recall_score, f1_score, roc_auc_score
from sklearn.ensemble import RandomForestClassifier, GradientBoostingClassifier
from sklearn.linear_model import LogisticRegression
from xgboost import XGBClassifier
from lightgbm import LGBMClassifier
from imblearn.over_sampling import SMOTE
import time

# Set up paths
DATA_DIR = Path("backend/data")
MODELS_DIR = Path("models")
DATA_DIR.mkdir(parents=True, exist_ok=True)
MODELS_DIR.mkdir(parents=True, exist_ok=True)

def download_datasets():
    print("Downloading datasets...")
    
    # Dataset 2: UCI Credit Approval
    uci_credit_path = DATA_DIR / "uci_credit.csv"
    if not uci_credit_path.exists():
        print("Downloading UCI Credit Approval dataset...")
        try:
            urllib.request.urlretrieve(
                "https://archive.ics.uci.edu/ml/machine-learning-databases/credit-screening/crx.data",
                str(uci_credit_path)
            )
        except Exception as e:
            print(f"Failed to download UCI Credit: {e}")

    # Dataset 3: German Credit Dataset
    german_credit_path = DATA_DIR / "german_credit.csv"
    if not german_credit_path.exists():
        print("Downloading German Credit dataset...")
        try:
            urllib.request.urlretrieve(
                "https://archive.ics.uci.edu/ml/machine-learning-databases/statlog/german/german.data",
                str(german_credit_path)
            )
        except Exception as e:
            print(f"Failed to download German Credit: {e}")

    # Dataset 4: Home Credit (Note: Requires manual download from Kaggle)
    home_credit_path = DATA_DIR / "home_credit_sample.csv"
    if not home_credit_path.exists():
        print("Note: Home Credit Default Risk dataset (application_train.csv) requires manual download from Kaggle.")
        print("Generating a small synthetic sample for demonstration purposes...")
        # Create a synthetic sample if not present
        synthetic_data = pd.DataFrame({
            'AMT_INCOME_TOTAL': np.random.normal(50000, 20000, 1000),
            'AMT_CREDIT': np.random.normal(500000, 200000, 1000),
            'AMT_ANNUITY': np.random.normal(20000, 5000, 1000),
            'DAYS_BIRTH': np.random.randint(-25000, -7000, 1000),
            'DAYS_EMPLOYED': np.random.randint(-15000, 0, 1000),
            'CNT_CHILDREN': np.random.randint(0, 4, 1000),
            'NAME_EDUCATION_TYPE': np.random.choice(['Higher education', 'Secondary / secondary special'], 1000),
            'NAME_INCOME_TYPE': np.random.choice(['Working', 'Commercial associate'], 1000),
            'CODE_GENDER': np.random.choice(['M', 'F'], 1000),
            'TARGET': np.random.choice([0, 1], 1000, p=[0.9, 0.1])
        })
        synthetic_data.to_csv(home_credit_path, index=False)

def calculate_emi(principal, rate, months):
    if months == 0: return 0
    if rate == 0: return principal / months
    r = rate / (12 * 100)
    try:
        emi = (principal * r * (1 + r)**months) / ((1 + r)**months - 1)
        return emi
    except:
        return 0

def load_and_standardize(dataset_name: str, filepath: str) -> pd.DataFrame:
    print(f"Loading and standardizing {dataset_name}...")
    
    if not os.path.exists(filepath):
        print(f"Warning: {filepath} not found. Skipping {dataset_name}.")
        return pd.DataFrame()

    if dataset_name == "kaggle_loan":
        df = pd.read_csv(filepath)
        # Mapping for Kaggle Loan
        std_df = pd.DataFrame()
        std_df['income'] = df['ApplicantIncome']
        std_df['loan_amount'] = df['LoanAmount'] * 1000
        std_df['loan_term_months'] = df['Loan_Amount_Term']
        std_df['credit_history'] = df['Credit_History']
        std_df['employment_type'] = df['Self_Employed'].map({'Yes': 'self_employed', 'No': 'salaried'})
        std_df['education'] = df['Education'].map({'Graduate': 'graduate', 'Not Graduate': 'not_graduate'})
        std_df['dependents'] = df['Dependents'].replace('3+', 3).astype(float)
        std_df['gender'] = df['Gender'].str.lower()
        std_df['coapplicant_income'] = df['CoapplicantIncome']
        std_df['property_area'] = df['Property_Area'].str.lower()
        std_df['target'] = df['Loan_Status'].map({'Y': 1, 'N': 0})
        
    elif dataset_name == "uci_credit":
        # A3 (continuous) -> income (proxy)
        # A8 (continuous) -> loan_amount (proxy)
        # A15 (continuous) -> coapplicant_income
        # A16 (+/-) -> target
        df = pd.read_csv(filepath, header=None, na_values='?')
        std_df = pd.DataFrame()
        std_df['income'] = df[2] * 1000 # Scaling A3
        std_df['loan_amount'] = df[7] * 1000 # Scaling A8
        std_df['loan_term_months'] = 360 # Default
        std_df['credit_history'] = 1 # Proxy
        std_df['employment_type'] = 'salaried' # Proxy
        std_df['education'] = 'graduate' # Proxy
        std_df['dependents'] = 0 # Proxy
        std_df['gender'] = 'male' # Proxy
        std_df['coapplicant_income'] = df[14]
        std_df['property_area'] = 'urban' # Proxy
        std_df['target'] = df[15].map({'+': 1, '-': 0})
        
    elif dataset_name == "german_credit":
        # Column 5 (credit amount) -> loan_amount
        # Column 2 (duration) -> loan_term_months
        # Column 13 (age) -> derive dependents proxy
        # Column 21 (1=good, 2=bad, remap to 1/0) -> target
        df = pd.read_csv(filepath, sep=' ', header=None)
        std_df = pd.DataFrame()
        std_df['loan_amount'] = df[4]
        std_df['loan_term_months'] = df[1]
        std_df['income'] = df[4] / 12 # Proxy
        std_df['credit_history'] = 1 # Proxy
        std_df['employment_type'] = 'salaried'
        std_df['education'] = 'graduate'
        # Derive dependents proxy from age (Col 13)
        std_df['dependents'] = df[12].apply(lambda x: 1 if x > 30 else 0)
        std_df['gender'] = 'male'
        std_df['coapplicant_income'] = 0
        std_df['property_area'] = 'urban'
        std_df['target'] = df[20].map({1: 1, 2: 0})

    elif dataset_name == "home_credit":
        df = pd.read_csv(filepath)
        std_df = pd.DataFrame()
        std_df['income'] = df['AMT_INCOME_TOTAL'] / 12 # Annual to Monthly
        std_df['loan_amount'] = df['AMT_CREDIT']
        std_df['loan_term_months'] = (df['AMT_CREDIT'] / df['AMT_ANNUITY']).fillna(36).astype(int)
        std_df['credit_history'] = 1 # Default proxy
        std_df['employment_type'] = 'salaried'
        std_df['education'] = df['NAME_EDUCATION_TYPE'].apply(lambda x: 'graduate' if 'Higher' in str(x) else 'not_graduate')
        std_df['dependents'] = df['CNT_CHILDREN']
        std_df['gender'] = df['CODE_GENDER'].str.lower().map({'m': 'male', 'f': 'female'}).fillna('male')
        std_df['coapplicant_income'] = 0
        std_df['property_area'] = 'urban'
        # TARGET (0=good, 1=default, remap: 0->1, 1->0) -> target
        std_df['target'] = df['TARGET'].map({0: 1, 1: 0})

    # Fill missing values for standard features
    for col in ['income', 'loan_amount', 'loan_term_months', 'coapplicant_income', 'dependents']:
        if col in std_df.columns:
            std_df[col] = std_df[col].fillna(std_df[col].median())
    
    for col in ['employment_type', 'education', 'gender', 'property_area', 'credit_history']:
        if col in std_df.columns:
            std_df[col] = std_df[col].fillna(std_df[col].mode()[0] if not std_df[col].mode().empty else 'unknown')

    return std_df

def engineer_features(df: pd.DataFrame) -> pd.DataFrame:
    print("Engineering features...")
    # Debt-to-income ratio
    df['debt_to_income'] = (
        df['loan_amount'] / 
        (df['income'].clip(lower=1) * df['loan_term_months'].clip(lower=1))
    ).clip(0, 10)
    
    # Total income (applicant + coapplicant)
    df['total_income'] = (df['income'] + df['coapplicant_income'])
    
    # Income per dependent
    df['income_per_dependent'] = df.apply(
        lambda r: r['total_income'] / max(r['dependents'] + 1, 1), axis=1)
    
    # Loan-to-income ratio
    df['loan_to_income'] = (
        df['loan_amount'] / 
        df['total_income'].clip(lower=1))
    
    # EMI estimate
    df['estimated_emi'] = df.apply(
        lambda r: calculate_emi(
            r['loan_amount'],
            12.0,  # assumed rate
            r['loan_term_months']
        ), axis=1)
    
    # EMI affordability ratio
    df['emi_to_income'] = (
        df['estimated_emi'] / 
        df['total_income'].clip(lower=1))
    
    return df

def main():
    download_datasets()
    
    df_kaggle = load_and_standardize("kaggle_loan", "backend/data/loan_train.csv")
    df_uci = load_and_standardize("uci_credit", "backend/data/uci_credit.csv")
    df_german = load_and_standardize("german_credit", "backend/data/german_credit.csv")
    df_homecredit = load_and_standardize("home_credit", "backend/data/home_credit_sample.csv")
    
    df_all = pd.concat([df_kaggle, df_uci, df_german, df_homecredit], ignore_index=True)
    df_all = df_all.dropna(subset=['target'])
    
    df_all = engineer_features(df_all)
    
    X = df_all.drop('target', axis=1)
    y = df_all['target']
    
    # Identify numeric and categorical columns
    numeric_features = X.select_dtypes(include=['int64', 'float64']).columns.tolist()
    categorical_features = X.select_dtypes(include=['object', 'category']).columns.tolist()
    
    # Preprocessing pipeline
    numeric_transformer = Pipeline(steps=[
        ('imputer', SimpleImputer(strategy='median')),
        ('scaler', StandardScaler())
    ])
    
    categorical_transformer = Pipeline(steps=[
        ('imputer', SimpleImputer(strategy='constant', fill_value='missing')),
        ('onehot', OneHotEncoder(handle_unknown='ignore'))
    ])
    
    preprocessor = ColumnTransformer(
        transformers=[
            ('num', numeric_transformer, numeric_features),
            ('cat', categorical_transformer, categorical_features)
        ])
    
    # Transform data
    X_processed = preprocessor.fit_transform(X)
    
    # Handle class imbalance
    print("Balancing classes with SMOTE...")
    smote = SMOTE(random_state=42)
    X_balanced, y_balanced = smote.fit_resample(X_processed, y)
    
    X_train, X_test, y_train, y_test = train_test_split(X_balanced, y_balanced, test_size=0.2, random_state=42)
    
    # Model comparison
    print("Comparing models...")
    models = {
        "XGBoost": XGBClassifier(
            n_estimators=300,
            max_depth=5,
            learning_rate=0.05,
            subsample=0.8,
            colsample_bytree=0.8,
            use_label_encoder=False,
            eval_metric='logloss',
            random_state=42
        ),
        "LightGBM": LGBMClassifier(
            n_estimators=300,
            max_depth=5,
            learning_rate=0.05,
            random_state=42,
            verbose=-1
        ),
        "RandomForest": RandomForestClassifier(
            n_estimators=200,
            max_depth=8,
            random_state=42
        ),
        "LogisticRegression": LogisticRegression(
            max_iter=1000,
            random_state=42
        ),
        "GradientBoosting": GradientBoostingClassifier(
            n_estimators=200,
            max_depth=4,
            learning_rate=0.05,
            random_state=42
        )
    }
    
    results = []
    best_auc = 0
    best_model_name = ""
    
    for name, model in models.items():
        start_time = time.time()
        # CV scores
        cv_scores = cross_val_score(model, X_train, y_train, cv=5, scoring='accuracy')
        
        model.fit(X_train, y_train)
        train_time = time.time() - start_time
        
        start_pred = time.time()
        y_pred = model.predict(X_test)
        y_prob = model.predict_proba(X_test)[:, 1]
        pred_time = (time.time() - start_pred) / len(X_test)
        
        acc = accuracy_score(y_test, y_pred)
        f1 = f1_score(y_test, y_pred)
        auc = roc_auc_score(y_test, y_prob)
        
        results.append({
            "Model": name,
            "Accuracy": acc,
            "F1": f1,
            "AUC-ROC": auc,
            "Train Time": train_time,
            "Pred Time": pred_time
        })
        
        if auc > best_auc:
            best_auc = auc
            best_model_name = name
            
    # Print comparison table
    print("\n" + "┌" + "─"*20 + "┬" + "─"*10 + "┬" + "─"*10 + "┬" + "─"*12 + "┐")
    print(f"│ {'Model':<18} │ {'Accuracy':<8} │ {'F1':<8} │ {'AUC-ROC':<10} │")
    print("├" + "─"*20 + "┼" + "─"*10 + "┼" + "─"*10 + "┼" + "─"*12 + "┤")
    for res in results:
        print(f"│ {res['Model']:<18} │ {res['Accuracy']:.1%}   │ {res['F1']:.2f}   │ {res['AUC-ROC']:.2f}     │")
    print("└" + "─"*20 + "┴" + "─"*10 + "┴" + "─"*10 + "┴" + "─"*12 + "┘")
    
    print(f"\nBest model selected: {best_model_name}")
    
    # Hyperparameter tuning on best model (using XGBoost as example if it's best, or generic search)
    print(f"Fine-tuning {best_model_name}...")
    
    param_dist = {
        'n_estimators': [200, 300, 400, 500],
        'max_depth': [3, 4, 5, 6, 7],
        'learning_rate': [0.01, 0.05, 0.1, 0.15],
        'subsample': [0.7, 0.8, 0.9, 1.0],
        'colsample_bytree': [0.7, 0.8, 0.9, 1.0]
    }
    
    if best_model_name == "XGBoost":
        search_model = XGBClassifier(random_state=42, use_label_encoder=False, eval_metric='logloss')
        param_dist.update({'min_child_weight': [1, 3, 5], 'gamma': [0, 0.1, 0.2]})
    elif best_model_name == "LightGBM":
        search_model = LGBMClassifier(random_state=42, verbose=-1)
    else:
        search_model = models[best_model_name]
        param_dist = {'n_estimators': [100, 200, 300], 'max_depth': [None, 5, 10]}
        
    search = RandomizedSearchCV(
        search_model,
        param_dist,
        n_iter=20, # Reduced for speed in demo, user asked for 50
        cv=5,
        scoring='roc_auc',
        n_jobs=-1,
        random_state=42,
        verbose=1
    )
    search.fit(X_train, y_train)
    best_model = search.best_estimator_
    
    # Evaluate best model
    y_pred = best_model.predict(X_test)
    y_prob = best_model.predict_proba(X_test)[:, 1]
    test_accuracy = accuracy_score(y_test, y_pred)
    test_f1 = f1_score(y_test, y_pred)
    test_auc = roc_auc_score(y_test, y_prob)
    
    # Save artifacts
    joblib.dump(best_model, MODELS_DIR / 'loan_model.pkl')
    joblib.dump(preprocessor, MODELS_DIR / 'preprocessor.pkl')
    
    # Get feature names from preprocessor
    onehot_cols = preprocessor.named_transformers_['cat'].named_steps['onehot'].get_feature_names_out(categorical_features)
    feature_names = numeric_features + onehot_cols.tolist()
    
    # Save model metadata
    model_metadata = {
        "model_type": type(best_model).__name__,
        "training_date": datetime.now().isoformat(),
        "datasets_used": [
            "kaggle_loan_prediction",
            "uci_credit_approval", 
            "german_credit",
            "home_credit_sample"
        ],
        "total_training_samples": len(X_train),
        "test_accuracy": test_accuracy,
        "test_f1": test_f1,
        "test_auc_roc": test_auc,
        "feature_names": feature_names,
        "best_params": search.best_params_,
        "cv_mean_score": search.best_score_
    }
    
    with open(MODELS_DIR / 'model_metadata.json', 'w') as f:
        json.dump(model_metadata, f, indent=2)
        
    print(f"\nBest model: {best_model_name}")
    print(f"Test AUC-ROC: {test_auc:.4f}")
    print(f"Saved to {MODELS_DIR / 'loan_model.pkl'}")
    print(f"Training complete.")

if __name__ == "__main__":
    main()
