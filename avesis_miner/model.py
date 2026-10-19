"""Test verisine bakmadan model seçimi, değerlendirme ve kalıcı model."""

import json
import math
from pathlib import Path

import joblib
import numpy as np
import sklearn
from sklearn.calibration import CalibratedClassifierCV
from sklearn.cluster import KMeans
from sklearn.dummy import DummyClassifier
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score, classification_report, f1_score
from sklearn.model_selection import StratifiedKFold, cross_val_score, train_test_split
from sklearn.pipeline import FeatureUnion, Pipeline
from sklearn.svm import LinearSVC

from .data import clean_records, load_records, normalize_text


def make_pipeline(kind="word", c=1.0, classifier="svm"):
    word = TfidfVectorizer(
        preprocessor=normalize_text, ngram_range=(1, 2), sublinear_tf=True, min_df=1, max_features=30000
    )
    char = TfidfVectorizer(
        preprocessor=normalize_text,
        analyzer="char_wb",
        ngram_range=(3, 5),
        sublinear_tf=True,
        min_df=2,
        max_features=50000,
    )
    features = {"word": word, "char": char, "combined": FeatureUnion([("word", word), ("char", char)])}[kind]
    estimator = (
        LinearSVC(C=c, class_weight="balanced", random_state=42, max_iter=10000)
        if classifier == "svm"
        else LogisticRegression(C=c, class_weight="balanced", max_iter=2000, random_state=42)
    )
    return Pipeline([("features", features), ("classifier", estimator)])


def calibrated(config, folds):
    # TF-IDF her kalibrasyon katının yalnızca eğitim bölümünde öğrenilir.
    return CalibratedClassifierCV(make_pipeline(**config), cv=folds, ensemble=False)


def metrics(y, probabilities, classes):
    order = np.argsort(-probabilities, axis=1)
    predictions = classes[order[:, 0]]
    k = min(3, len(classes))
    return {
        "accuracy": float(accuracy_score(y, predictions)),
        "macro_f1": float(f1_score(y, predictions, average="macro", zero_division=0)),
        "weighted_f1": float(f1_score(y, predictions, average="weighted", zero_division=0)),
        "top_3_accuracy": float(np.mean([label in classes[row[:k]] for label, row in zip(y, order)])),
        "classification_report": classification_report(y, predictions, zero_division=0, output_dict=True),
    }


def train(data_path, output_dir, min_samples=10, test_size=0.2, seed=42, clusters=15):
    if min_samples < 5:
        raise ValueError("Bölme ve kalibrasyon için min-samples en az 5 olmalı.")
    if not 0 < test_size < 1:
        raise ValueError("test-size 0 ile 1 arasında olmalı.")
    if clusters < 0:
        raise ValueError("Küme sayısı negatif olamaz; kapatmak için 0 kullanın.")
    data, cleaning = clean_records(load_records(data_path), min_samples)
    if data["author"].nunique() < 2:
        raise ValueError(
            "Filtreleme sonrasında en az iki yazar gerekli. Veri ekleyin veya min-samples değerini azaltın (en az 5)."
        )
    n_test = max(data["author"].nunique(), math.ceil(len(data) * test_size))
    if len(data) - n_test < data["author"].nunique() * 3:
        raise ValueError("Eğitimde yazar başına en az 3 örnek kalmalı; test-size değerini azaltın.")
    train_df, test_df = train_test_split(data, test_size=n_test, stratify=data["author"], random_state=seed)
    folds = min(3, int(train_df["author"].value_counts().min()))
    if folds < 3:
        raise ValueError("Eğitimde her yazar için en az 3 örnek kalmalı; test-size değerini azaltın.")
    cv = StratifiedKFold(n_splits=folds, shuffle=True, random_state=seed)
    configs = [dict(kind="word", c=1.0, classifier="svm")]
    configs += [dict(kind=kind, c=c, classifier="svm") for kind in ("char", "combined") for c in (1.0, 3.0)]
    configs += [dict(kind="combined", c=3.0, classifier="logistic")]
    candidates = []
    for config in configs:
        scores = cross_val_score(
            make_pipeline(**config),
            train_df["title"],
            train_df["author"],
            cv=cv,
            scoring="f1_macro",
            error_score="raise",
        )
        candidates.append(
            {"config": config, "cv_macro_f1": float(scores.mean()), "cv_std": float(scores.std())}
        )
        print(f"  {config}: CV macro-F1={scores.mean():.4f}", flush=True)
    best = max(candidates, key=lambda row: row["cv_macro_f1"])
    model = calibrated(best["config"], cv)
    model.fit(train_df["title"], train_df["author"])
    evaluation = metrics(test_df["author"].to_numpy(), model.predict_proba(test_df["title"]), model.classes_)
    baseline = calibrated(configs[0], cv)
    baseline.fit(train_df["title"], train_df["author"])
    baseline_metrics = metrics(
        test_df["author"].to_numpy(), baseline.predict_proba(test_df["title"]), baseline.classes_
    )
    dummy = DummyClassifier(strategy="most_frequent").fit(train_df["title"], train_df["author"])
    report = {
        "schema_version": 1,
        "target": "first_author",
        "sklearn_version": sklearn.__version__,
        "seed": seed,
        "min_samples": min_samples,
        "cleaning": cleaning,
        "train_rows": len(train_df),
        "test_rows": len(test_df),
        "class_counts": {str(k): int(v) for k, v in data["author"].value_counts().items()},
        "candidates": candidates,
        "selected": best["config"],
        "test": evaluation,
        "word_svm_baseline_test": baseline_metrics,
        "majority_accuracy": float(accuracy_score(test_df["author"], dummy.predict(test_df["title"]))),
        "accuracy_difference_vs_baseline": evaluation["accuracy"] - baseline_metrics["accuracy"],
        "selection_rule": "Training-only stratified CV macro-F1; holdout evaluated after selection.",
        "limitations": [
            "First-author names may identify multiple people.",
            "Near-duplicate titles may remain; exact normalized duplicates are removed.",
            "Random title split does not measure future-year or unseen-author generalization.",
            "Final artifact is refitted on all eligible data; metrics belong to the held-out evaluation model.",
        ],
    }
    final_cv = StratifiedKFold(n_splits=folds, shuffle=True, random_state=seed)
    final = calibrated(best["config"], final_cv).fit(data["title"], data["author"])
    features = final.calibrated_classifiers_[0].estimator.named_steps["features"]
    cluster_model = None
    if clusters:
        vectors = features.transform(data["title"])
        n_clusters = min(clusters, len(data), len({normalize_text(t) for t in data["title"]}))
        cluster_model = KMeans(n_clusters=n_clusters, random_state=seed, n_init=10).fit(vectors)
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    artifact = {
        "schema_version": 1,
        "model": final,
        "clusters": cluster_model,
        "sklearn_version": sklearn.__version__,
        "report": report,
    }
    temporary = output / "model.joblib.tmp"
    joblib.dump(artifact, temporary)
    temporary.replace(output / "model.joblib")
    (output / "metrics.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return report


def load_model(path):
    artifact = joblib.load(path)
    if not isinstance(artifact, dict) or artifact.get("schema_version") != 1:
        raise ValueError("Desteklenmeyen model dosyası; modeli yeniden eğitin.")
    if artifact.get("sklearn_version") != sklearn.__version__:
        raise ValueError("Modelin scikit-learn sürümü farklı; mevcut ortamda yeniden eğitin.")
    return artifact


def predict(artifact, title, top_k=3, threshold=0.10):
    if top_k < 1 or not 0 <= threshold <= 1:
        raise ValueError("top-k pozitif, threshold 0 ile 1 arasında olmalı.")
    if not normalize_text(title):
        return {"status": "empty", "candidates": [], "cluster": None}
    model = artifact["model"]
    features = model.calibrated_classifiers_[0].estimator.named_steps["features"]
    vec = features.transform([title])
    if vec.nnz == 0:
        return {"status": "unknown_vocabulary", "candidates": [], "cluster": None}
    probabilities = model.predict_proba([title])[0]
    indices = np.argsort(-probabilities)[:top_k]
    cluster = artifact.get("clusters")
    return {
        "status": "low_confidence" if probabilities[indices[0]] < threshold else "ok",
        "candidates": [
            {"author": str(model.classes_[i]), "probability": float(probabilities[i])} for i in indices
        ],
        "cluster": int(cluster.predict(vec)[0]) if cluster is not None else None,
    }
