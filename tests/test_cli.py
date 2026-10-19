from avesis_miner.cli import main


def test_missing_file_returns_error_instead_of_traceback(capsys):
    assert main(["inspect", "--data", "this-file-does-not-exist.csv"]) == 1
    assert "Hata:" in capsys.readouterr().err


def test_inspect_sample_data(capsys):
    assert main(["inspect", "--data", "examples/publications.csv"]) == 0
    assert '"usable_rows": 20' in capsys.readouterr().out


def test_invalid_predict_options_are_checked_before_model_loading(capsys):
    assert main(["predict", "--model", "missing.joblib", "--top-k", "0"]) == 1
    assert "top-k" in capsys.readouterr().err
