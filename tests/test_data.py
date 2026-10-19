import pandas as pd
import pytest

from avesis_miner.data import clean_records, load_records, normalize_text, read_links, save_records


def test_cleaning_removes_duplicates_conflicts_and_invalid_rows():
    raw = pd.DataFrame(
        {
            "title": ["A title!", "a title", "Conflict", "conflict.", "", None, "Unique"],
            "author": ["Author A", "Author A", "Author A", "Author B", "A", "B", "Author C"],
        }
    )
    data, stats = clean_records(raw)
    assert data["title"].tolist() == ["A title!", "Unique"]
    assert stats["duplicate_rows"] == 1
    assert stats["conflicting_titles"] == 1
    assert stats["conflicting_rows"] == 2
    assert stats["invalid_rows"] == 2


def test_turkish_and_numbers_are_preserved():
    assert normalize_text("İŞLEM IŞIK 2026!") == "işlem ışık 2026"


@pytest.mark.parametrize("suffix", [".csv", ".xlsx"])
def test_legacy_schema_and_extra_columns_roundtrip(tmp_path, suffix):
    path = tmp_path / ("publications" + suffix)
    raw = pd.DataFrame(
        {"Makale Başlığı": ["Örnek başlık"], "Yazar 1": ["Yılmaz A."], "Yazar 2": ["Başka B."]}
    )
    save_records(raw, path)
    loaded = load_records(path)
    assert loaded.loc[0, "title"] == "Örnek başlık"
    assert loaded.loc[0, "author"] == "Yılmaz A."
    assert "Yazar 2" in loaded


def test_profile_list_headers_comments_and_duplicates(tmp_path):
    path = tmp_path / "profiles.txt"
    path.write_text("# açıklama\nhttps://avesis.test/a\nhttps://avesis.test/a\n", encoding="utf-8")
    assert read_links(path) == ["https://avesis.test/a"]


def test_invalid_schema_is_actionable(tmp_path):
    path = tmp_path / "wrong.csv"
    path.write_text("name,value\na,b\n", encoding="utf-8")
    with pytest.raises(ValueError, match="title ve author"):
        load_records(path)


def test_duplicate_alias_columns_are_rejected(tmp_path):
    path = tmp_path / "wrong.csv"
    path.write_text("title,Makale Başlığı,author\na,a,b\n", encoding="utf-8")
    with pytest.raises(ValueError, match="birden fazla"):
        load_records(path)
