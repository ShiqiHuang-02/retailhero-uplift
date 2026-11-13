"""Exploratory additions. Never fit on the original test data."""
import copy
import numpy as np
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.pipeline import Pipeline
from sklearn.impute import SimpleImputer
from sklearn.preprocessing import OneHotEncoder, StandardScaler
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import train_test_split
from sklearn.metrics import roc_auc_score, brier_score_loss, log_loss
from src.audit_core import effect_scores, normal_summary, paired_summary, bootstrap_topk


def validate_frame(data):
    if len(data) < 2 or data.client_id.isna().any() or not data.client_id.is_unique:
        raise ValueError("Customer IDs must be unique, nonmissing, and contain at least two customers")
    for column in ["treatment_flg", "target"]:
        if data[column].isna().any() or not data[column].isin([0, 1]).all():
            raise ValueError(f"Invalid {column}")


def validate_splits(train, valid, test):
    for frame in (train, valid, test):
        validate_frame(frame)
    ids = [set(f.client_id) for f in (train, valid, test)]
    if any(ids[i] & ids[j] for i, j in [(0, 1), (0, 2), (1, 2)]):
        raise ValueError("Customer leakage across train/validation/test")


def make_classifier(config, treatment_feature=False, seed=42):
    numeric = list(config["numeric_features"])
    if treatment_feature:
        numeric.append("treatment_flg")
    pre = ColumnTransformer([
        ("numeric", SimpleImputer(strategy="median"), numeric),
        ("categorical", OneHotEncoder(handle_unknown="ignore", sparse_output=False), config["categorical_features"])
    ])
    model = HistGradientBoostingClassifier(learning_rate=.05, max_iter=150,
        max_leaf_nodes=15, min_samples_leaf=100, l2_regularization=1.,
        early_stopping=True, random_state=seed)
    return Pipeline([("preprocessing", pre), ("classifier", model)])


def fit_response_models(train, config):
    validate_frame(train)
    x = train[config["feature_columns"]]
    models = {}
    for name, mask in [("response", np.ones(len(train), dtype=bool)),
                       ("m0", train.treatment_flg.eq(0)), ("m1", train.treatment_flg.eq(1))]:
        if train.loc[mask, "target"].nunique() < 2:
            raise ValueError("Both outcome classes are required in each model training subset")
        models[name] = make_classifier(config).fit(x.loc[mask], train.loc[mask, "target"])
    return models


def predict_response_models(data, models, config):
    result = data.copy().reset_index(drop=True)
    x = result[config["feature_columns"]]
    for model, column in [("response", "response_score"), ("m0", "p0"), ("m1", "p1")]:
        result[column] = models[model].predict_proba(x)[:, 1]
    result["uplift_score"] = result.p1 - result.p0
    return result


def fit_propensity(train, config):
    validate_frame(train)
    numeric = Pipeline([("imputer", SimpleImputer(strategy="median")), ("scale", StandardScaler())])
    preprocessing = ColumnTransformer([
        ("numeric", numeric, config["numeric_features"]),
        ("categorical", OneHotEncoder(handle_unknown="ignore", sparse_output=False), config["categorical_features"])
    ])
    model = Pipeline([("preprocessing", preprocessing),
                      ("classifier", LogisticRegression(C=1., max_iter=3000, random_state=42))])
    return model.fit(train[config["feature_columns"]], train.treatment_flg)


def propensity_sensitivity(train, evaluation, config, policy_config):
    """Return estimates, diagnostics and raw probabilities; fit only on train."""
    if set(train.client_id) & set(evaluation.client_id):
        raise ValueError("Propensity fitting and evaluation customers overlap")
    model = fit_propensity(train, config)
    raw = model.predict_proba(evaluation[config["feature_columns"]])[:, 1]
    e = np.clip(raw, .01, .99)  # Predeclared numerical protection; always disclose clipping.
    treatments = evaluation.treatment_flg.to_numpy()
    diagnostics = dict(auc=roc_auc_score(treatments, raw),
        brier=brier_score_loss(treatments, raw), log_loss=log_loss(treatments, raw),
        min=float(raw.min()), p01=float(np.quantile(raw, .01)),
        median=float(np.median(raw)), p99=float(np.quantile(raw, .99)), max=float(raw.max()),
        clipped_fraction=float(np.mean(raw != e)), clip_low=.01, clip_high=.99,
        training_treatment_share=float(train.treatment_flg.mean()))
    for label, weights in [("treated", treatments/e), ("control", (1-treatments)/(1-e))]:
        diagnostics[label + "_ess"] = float(weights.sum()**2 / np.square(weights).sum())
    gains, contrasts = [], []
    scenarios = {"assumed_0.5": .5, "training_share": float(train.treatment_flg.mean()), "logistic_eX": e}
    for scenario, probability in scenarios.items():
        for method in ["DR", "IPW"]:
            a, b = evaluate_policies(evaluation, policy_config, method, probability)
            for table, collection in [(a, gains), (b, contrasts)]:
                table["propensity_scenario"] = scenario
                table["method"] = method
                collection.append(table)
    return pd.concat(gains, ignore_index=True), pd.concat(contrasts, ignore_index=True), pd.DataFrame([diagnostics]), raw, model


def build_policies(data, config):
    validate_frame(data)
    df = data.copy().reset_index(drop=True)
    budget = float(config["budget_share"])
    if not 0 <= budget <= 1:
        raise ValueError("Budget must be in [0,1]")
    def rfm_bin(column):
        values = df[column].to_numpy(dtype=float)
        edges = np.asarray(config["rfm_thresholds"][column], dtype=float)
        if not np.isfinite(values).all() or len(edges) != 4 or not np.isfinite(edges).all() or (np.diff(edges) < 0).any():
            raise ValueError("Invalid RFM values or training thresholds")
        return np.searchsorted(edges, values, side="right")
    df["rfm_score"] = 4 - rfm_bin("recency_days") + rfm_bin("txn_count_history") + rfm_bin("spend_history")
    n = len(df)
    k = int(round(n * budget))
    policies = {"Random": np.full(n, k/n)}
    for name, column in config["ranking_columns"].items():
        if not np.isfinite(df[column].to_numpy(dtype=float)).all():
            raise ValueError(f"Nonfinite score: {column}")
        # Match bootstrap lexicographic tie-breaking even for numeric identifiers.
        ordered = df.assign(_tie_id=df.client_id.astype(str)).sort_values([column, "_tie_id"], ascending=[False, True])
        mask = np.zeros(n)
        mask[ordered.index[:k].to_numpy()] = 1
        policies[name] = mask
        if int(mask.sum()) != k:
            raise AssertionError("Incorrect contact count")
    return df, policies


def evaluate_policies(data, config, method="DR", propensity=None):
    df, policies = build_policies(data, config)
    e = config["propensity"] if propensity is None else propensity
    gamma = np.asarray(effect_scores(df.treatment_flg, df.target, df.p0, df.p1, e, method))
    gain_rows, contrast_rows = [], []
    for name, policy in policies.items():
        avg, lo, hi = normal_summary(policy * gamma)
        gain_rows.append(dict(strategy=name, contacts_per_1000=policy.mean()*1000,
            gain_per_1000=avg, ci_low=lo, ci_high=hi))
    for baseline in config["comparison_baselines"]:
        avg, lo, hi = paired_summary(gamma, policies["Uplift"], policies[baseline])
        contrast_rows.append(dict(comparison=f"Uplift - {baseline}", extra_gain_per_1000=avg, ci_low=lo, ci_high=hi))
    return pd.DataFrame(gain_rows), pd.DataFrame(contrast_rows)


def customer_profiles(evaluation, policy_config):
    df, policies = build_policies(evaluation, policy_config)
    features = ["age_clean", "age_review_flag", "recency_days", "txn_count_history", "txn_count_30d", "spend_history", "spend_30d", "avg_transaction_amount"]
    groups = {"All": np.ones(len(df), dtype=bool),
              **{name: policies[name].astype(bool) for name in ["Uplift", "Response", "Response_p1"]}}
    numeric, categorical, overlap = [], [], []
    for name, mask in groups.items():
        frame = df.loc[mask]
        for col in features:
            numeric.append(dict(group=name, feature=col, customers=len(frame),
                nonmissing=int(frame[col].notna().sum()), mean=frame[col].mean(),
                median=frame[col].median(), q25=frame[col].quantile(.25), q75=frame[col].quantile(.75)))
        for category in sorted(df.gender.fillna("Missing").astype(str).unique()):
            count = int(frame.gender.fillna("Missing").astype(str).eq(category).sum())
            categorical.append(dict(group=name, gender=category, count=count,
                                    proportion=count/len(frame) if len(frame) else np.nan))
    u = groups["Uplift"]
    for name in ["Response", "Response_p1"]:
        b = groups[name]
        both, union = int((u & b).sum()), int((u | b).sum())
        overlap.append(dict(comparison="Uplift vs " + name, intersection=both,
            selected_each=int(u.sum()), overlap_share=both/u.sum() if u.sum() else np.nan,
            jaccard=both/union if union else np.nan))
    return pd.DataFrame(numeric), pd.DataFrame(categorical), pd.DataFrame(overlap)


def bootstrap_policies(evaluation, policy_config, repeats=500, seed=20261113):
    df, _ = build_policies(evaluation, policy_config)
    gamma = effect_scores(df.treatment_flg, df.target, df.p0, df.p1, policy_config["propensity"])
    rankings = {name: df[column].tolist() for name, column in policy_config["ranking_columns"].items()}
    return pd.DataFrame(bootstrap_topk(gamma, rankings, df.client_id.tolist(),
        budget=policy_config["budget_share"], repeats=repeats, seed=seed))


def slearner_comparison(train, evaluation, config, policy_config):
    """Compare score rules using the same T-learner DR evaluator for fairness."""
    if set(train.client_id) & set(evaluation.client_id):
        raise ValueError("S-learner fitting/evaluation overlap")
    columns = config["feature_columns"] + ["treatment_flg"]
    model = make_classifier(config, treatment_feature=True).fit(train[columns], train.target)
    df = evaluation.copy()
    x = df[columns].copy()
    df["slearner_score"] = model.predict_proba(x.assign(treatment_flg=1))[:, 1] - model.predict_proba(x.assign(treatment_flg=0))[:, 1]
    settings = copy.deepcopy(policy_config)
    settings["ranking_columns"]["Slearner"] = "slearner_score"
    settings["comparison_baselines"] = list(settings["comparison_baselines"]) + ["Slearner"]
    tables = {}
    for method in ["DR", "IPW"]:
        gains, contrasts = evaluate_policies(df, settings, method)
        tables[method] = (gains.assign(method=method), contrasts.assign(method=method))
    return pd.concat([v[0] for v in tables.values()], ignore_index=True), pd.concat([v[1] for v in tables.values()], ignore_index=True), model


def repeated_split_stability(train, valid, test, config, policy_config, seeds=(101, 202, 303, 404, 505)):
    """Descriptive repeated development splits. The original test is never predicted."""
    validate_splits(train, valid, test)
    development = pd.concat([train, valid], ignore_index=True)
    rows = []
    for seed in seeds:
        fit, holdout = train_test_split(development, test_size=len(valid)/len(development),
            stratify=development.treatment_flg, random_state=seed)
        models = fit_response_models(fit, config)
        scored = predict_response_models(holdout, models, config)
        settings = copy.deepcopy(policy_config)
        settings["rfm_thresholds"] = {col: fit[col].quantile([.2, .4, .6, .8]).tolist()
                                      for col in ["recency_days", "txn_count_history", "spend_history"]}
        for method in ["DR", "IPW"]:
            _, contrasts = evaluate_policies(scored, settings, method)
            contrasts["split_seed"] = seed
            contrasts["method"] = method
            contrasts["fit_customers"] = len(fit)
            contrasts["evaluation_customers"] = len(holdout)
            rows.append(contrasts)
    details = pd.concat(rows, ignore_index=True)
    summary = details.groupby(["method", "comparison"], as_index=False).agg(
        repetitions=("split_seed", "size"), descriptive_mean=("extra_gain_per_1000", "mean"),
        descriptive_sd=("extra_gain_per_1000", "std"), minimum=("extra_gain_per_1000", "min"),
        maximum=("extra_gain_per_1000", "max"),
        positive_point_estimates=("extra_gain_per_1000", lambda x: int((x > 0).sum())))
    return details, summary
