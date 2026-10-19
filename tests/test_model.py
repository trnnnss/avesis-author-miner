import numpy as np
import pytest

from avesis_miner.model import load_model, make_pipeline, metrics, predict, train


def test_vectorizer_does_not_learn_unseen_test_word():
    pipeline = make_pipeline()
    pipeline.fit(["image networks", "image segmentation", "soil farming", "soil crops"], ["A", "A", "B", "B"])
    assert pipeline.named_steps["features"].transform(["unseenholdouttoken"]).nnz == 0


def test_top_three_works_for_binary_data():
    report = metrics(np.array(["A", "B"]), np.array([[0.9, 0.1], [0.7, 0.3]]), np.array(["A", "B"]))
    assert report["accuracy"] == 0.5
    assert report["top_3_accuracy"] == 1


@pytest.fixture(scope="module")
def trained(tmp_path_factory):
    output = tmp_path_factory.mktemp("model")
    report = train("examples/publications.csv", output, clusters=2)
    return report, load_model(output / "model.joblib")


def test_full_training_persistence_and_probability_predictions(trained):
    report, artifact = trained
    assert report["test_rows"] == 4
    assert len(report["candidates"]) == 6
    result = predict(artifact, "Neural networks for image classification")
    assert result["candidates"][0]["author"] == "Ada Example"
    assert sum(c["probability"] for c in result["candidates"]) == pytest.approx(1)
    assert result["cluster"] in (0, 1)


def test_empty_and_unknown_inputs(trained):
    _, artifact = trained
    assert predict(artifact, "   ")["status"] == "empty"
    assert predict(artifact, "zzzzqqqqxxxx")["status"] == "unknown_vocabulary"


def test_bad_training_configuration_rejected(tmp_path):
    with pytest.raises(ValueError, match="en az 5"):
        train("examples/publications.csv", tmp_path, min_samples=2)
