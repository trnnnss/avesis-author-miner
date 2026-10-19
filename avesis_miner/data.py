"""Dosya girişi, ortak şema ve deterministik veri temizliği."""

import re
import unicodedata
from pathlib import Path

import pandas as pd

ALIASES = {
    "title": "title",
    "makale başlığı": "title",
    "başlık": "title",
    "author": "author",
    "yazar 1": "author",
    "yazar": "author",
    "source_url": "source_url",
    "kaynak": "source_url",
}


def normalize_text(value: str) -> str:
    text = unicodedata.normalize("NFKC", str(value)).replace("İ", "i").replace("I", "ı").lower()
    text = text.replace("\u0307", "")
    return " ".join(re.sub(r"[^\w\s]", " ", text, flags=re.UNICODE).split())


def read_table(path: str | Path, *, header="infer") -> pd.DataFrame:
    path = Path(path)
    if path.suffix.lower() == ".xlsx":
        return pd.read_excel(path, header=0 if header == "infer" else header)
    if path.suffix.lower() == ".csv":
        return pd.read_csv(path, header=header, encoding="utf-8-sig")
    raise ValueError("Desteklenen veri dosyaları: .csv ve .xlsx")


def load_records(path: str | Path) -> pd.DataFrame:
    df = read_table(path)
    df = df.rename(columns={c: ALIASES.get(str(c).strip().lower(), c) for c in df.columns})
    if df.columns.duplicated().any():
        raise ValueError("Aynı anlama gelen birden fazla sütun var; title ve author tekil olmalı.")
    if not {"title", "author"}.issubset(df.columns):
        raise ValueError(
            "Veri dosyasında title ve author (veya Makale Başlığı ve Yazar 1) sütunları gerekli."
        )
    return df


def clean_records(df: pd.DataFrame, min_samples: int = 1):
    if min_samples < 1:
        raise ValueError("Minimum örnek sayısı pozitif olmalı.")
    data = df.copy()
    stats = {"input_rows": len(data)}
    data = data.dropna(subset=["title", "author"])
    for col in ("title", "author"):
        data[col] = data[col].astype(str).map(lambda x: " ".join(unicodedata.normalize("NFKC", x).split()))
    data["_key"] = data["title"].map(normalize_text)
    data["_author_key"] = data["author"].map(normalize_text)
    data = data[(data["_key"] != "") & (data["_author_key"] != "")].copy()
    stats["invalid_rows"] = stats["input_rows"] - len(data)
    canonical = dict(zip(data["_author_key"], data["author"]))
    data["author"] = data["_author_key"].map(canonical)
    conflicts = data.groupby("_key")["_author_key"].nunique()
    conflict_keys = conflicts[conflicts > 1].index
    stats["conflicting_titles"] = len(conflict_keys)
    stats["conflicting_rows"] = int(data["_key"].isin(conflict_keys).sum())
    data = data[~data["_key"].isin(conflict_keys)]
    before = len(data)
    data = data.drop_duplicates("_key")
    stats["duplicate_rows"] = before - len(data)
    counts = data["author"].value_counts()
    data = data[data["author"].isin(counts[counts >= min_samples].index)]
    stats["excluded_rare_rows"] = before - stats["duplicate_rows"] - len(data)
    data = data.drop(columns=["_key", "_author_key"]).reset_index(drop=True)
    stats.update(usable_rows=len(data), authors=int(data["author"].nunique()))
    return data, stats


def save_records(df: pd.DataFrame, path: str | Path):
    """Aynı klasörde geçici dosya + replace ile yarım çıktı bırakma."""
    path = Path(path)
    if path.suffix.lower() not in {".csv", ".xlsx"}:
        raise ValueError("Çıktı uzantısı .csv veya .xlsx olmalı.")
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(path.stem + ".tmp" + path.suffix)
    try:
        if path.suffix.lower() == ".xlsx":
            df.to_excel(temp, index=False)
        else:
            df.to_csv(temp, index=False, encoding="utf-8-sig")
        temp.replace(path)
    finally:
        temp.unlink(missing_ok=True)


def read_links(path: str | Path) -> list[str]:
    path = Path(path)
    if path.suffix.lower() == ".txt":
        values = path.read_text(encoding="utf-8-sig").splitlines()
    else:
        values = read_table(path, header=None).iloc[:, 0].dropna().astype(str)
    links = []
    for value in values:
        value = value.strip()
        if not value or value.startswith("#") or value.lower() in {"url", "link", "linkler", "profile_url"}:
            continue
        if not value.startswith(("https://", "http://")):
            raise ValueError(f"Geçersiz bağlantı: {value}")
        links.append(value)
    if not links:
        raise ValueError("Dosyada profil bağlantısı bulunamadı.")
    return list(dict.fromkeys(links))
