from types import SimpleNamespace

import pandas as pd
import pytest

from avesis_miner.data import load_records, save_records
from avesis_miner.scraping import Client, discover_profiles, parse_publications, publication_url, scrape

HTML = """<div class="pub-item with-icon"><strong>Örnek çalışma</strong>
<a class="authorsRichText">AYDIN Y.</a><a class="authorsRichText">Kaya A.</a></div>
<a href="?page=2">2</a><a href="https://other.test/user/yayinlar?page=3">3</a>"""


def test_parser_first_author_and_pagination():
    rows, pages, count = parse_publications(HTML, "https://avesis.test/user/yayinlar")
    assert rows[0]["author"] == "AYDIN Y."
    assert rows[0]["authors"] == "AYDIN Y. | Kaya A."
    assert pages == ["https://avesis.test/user/yayinlar?page=2"]
    assert count == 1


def test_profile_urls_and_discovery():
    assert (
        publication_url("https://avesis.test/username/yayinlar/?page=1")
        == "https://avesis.test/username/yayinlar"
    )
    with pytest.raises(ValueError):
        publication_url("https://avesis.test/arama")
    links = discover_profiles(
        '<a href="/baran">A</a><a href="/username/yayinlar">B</a><a href="/arama">search</a>',
        "https://avesis.test/arama",
    )
    assert links == ["https://avesis.test/baran", "https://avesis.test/username"]


class FakeClient:
    def __init__(self, html):
        self.html = html

    def get(self, url):
        return SimpleNamespace(text=self.html, url=url)


def test_existing_three_column_data_survives_update(tmp_path):
    output = tmp_path / "data.csv"
    save_records(pd.DataFrame({"title": ["Old"], "author": ["A"], "Yazar 2": ["B"]}), output)
    report = scrape(["https://avesis.test/user"], output, client=FakeClient(HTML), max_pages=2)
    data = load_records(output)
    assert len(data) == 2
    assert data.loc[0, "Yazar 2"] == "B"
    assert report["fetched_rows"] == 2


def test_empty_scrape_preserves_existing_file(tmp_path):
    output = tmp_path / "data.csv"
    output.write_text("title,author\nold,A\n", encoding="utf-8")
    before = output.read_bytes()
    with pytest.raises(ValueError, match="Hiç yayın"):
        scrape(["https://avesis.test/user"], output, client=FakeClient("<html></html>"))
    assert output.read_bytes() == before


def test_robots_denial_prevents_profile_request(monkeypatch):
    client = Client()
    visited = []

    def fake_request(url, delay):
        visited.append(url)
        return SimpleNamespace(status_code=200, text="User-agent: *\nDisallow: /\n")

    monkeypatch.setattr(client, "_request", fake_request)
    with pytest.raises(ValueError, match="izin vermiyor"):
        client.get("https://avesis.test/user/yayinlar")
    assert visited == ["https://avesis.test/robots.txt"]
    client.close()
