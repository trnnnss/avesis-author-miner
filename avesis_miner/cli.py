"""Kullanıcıya açık komutlar; içe aktarırken ağ, eğitim veya dosya yazımı yoktur."""

import argparse
import json
import logging
import sys
from pathlib import Path

from .data import clean_records, load_records, read_links


def parser():
    root = argparse.ArgumentParser(description="AVESİS yayın tarama ve ilk yazar tahmini")
    root.add_argument("--verbose", action="store_true")
    commands = root.add_subparsers(dest="command", required=True)
    scan = commands.add_parser("scrape", help="Kendi profil listenizden yayınları toplayın")
    scan.add_argument("--links", required=True, type=Path)
    scan.add_argument("--output", type=Path, default=Path("data/publications.csv"))
    scan.add_argument("--max-pages", type=int, default=10)
    scan.add_argument("--max-publications", type=int, default=0, help="Profil başına limit; 0 sınırsız")
    scan.add_argument("--delay", type=float, default=1.0)
    scan.add_argument("--timeout", type=float, default=20)
    discover = commands.add_parser(
        "discover", help="Verilen dizin sayfalarının HTML profil bağlantılarını bulun"
    )
    discover.add_argument("--pages", required=True, type=Path, help="Dizin URL listesi (.txt/.csv/.xlsx)")
    discover.add_argument("--output", type=Path, default=Path("data/profiles.txt"))
    discover.add_argument("--delay", type=float, default=1.0)
    learn = commands.add_parser("train", help="Hazır CSV/Excel dosyasından model eğitin")
    learn.add_argument("--data", required=True, type=Path)
    learn.add_argument("--output-dir", type=Path, default=Path("artifacts"))
    learn.add_argument("--min-samples", type=int, default=10)
    learn.add_argument("--test-size", type=float, default=0.2)
    learn.add_argument("--seed", type=int, default=42)
    learn.add_argument("--clusters", type=int, default=15, help="Küme sayısı; 0 kapatır")
    infer = commands.add_parser("predict", help="Kaydedilmiş modelle başlık tahmini")
    infer.add_argument("--model", required=True, type=Path)
    infer.add_argument("--title", help="Verilmezse etkileşimli başlık girişi")
    infer.add_argument("--top-k", type=int, default=3)
    infer.add_argument("--threshold", type=float, default=0.10)
    check = commands.add_parser("inspect", help="Veri kalitesini eğitim yapmadan raporlayın")
    check.add_argument("--data", required=True, type=Path)
    check.add_argument("--min-samples", type=int, default=10)
    return root


def show_prediction(result):
    messages = {
        "empty": "Başlık boş; anlamlı bir metin girin.",
        "unknown_vocabulary": "Eğitim sözlüğüyle eşleşme bulunamadı; tahmin üretilmedi.",
        "low_confidence": "Düşük olasılık: sonuç belirsiz.",
    }
    if result["status"] in messages:
        print(messages[result["status"]])
    if result["cluster"] is not None:
        print(f"Benzerlik kümesi: {result['cluster']} (bilim alanı etiketi değildir)")
    for i, row in enumerate(result["candidates"], 1):
        print(f"{i}. {row['author']}: %{row['probability'] * 100:.2f}")


def main(argv=None):
    args = parser().parse_args(argv)
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO, format="%(levelname)s: %(message)s"
    )
    try:
        if args.command == "inspect":
            _, report = clean_records(load_records(args.data), args.min_samples)
            print(json.dumps(report, ensure_ascii=False, indent=2))
        elif args.command == "scrape":
            from .scraping import scrape

            report = scrape(
                read_links(args.links),
                args.output,
                max_pages=args.max_pages,
                max_publications=args.max_publications,
                delay=args.delay,
                timeout=args.timeout,
            )
            report_path = args.output.with_suffix(".scrape.json")
            report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
            print(f"{report['saved_rows']} kayıt: {args.output}; tarama raporu: {report_path}")
            if any(p["errors"] or p["page_limit_reached"] for p in report["profiles"]):
                print("Tarama kısmen tamamlandı veya sayfa limitine ulaşıldı; raporu inceleyin.")
        elif args.command == "discover":
            from .scraping import Client, discover_profiles

            client = Client(delay=args.delay)
            links = set()
            try:
                for page in read_links(args.pages):
                    response = client.get(page)
                    links.update(discover_profiles(response.text, response.url))
            finally:
                client.close()
            if not links:
                raise ValueError(
                    "HTML içinde profil bağlantısı bulunamadı. JavaScript ile yüklenen dizinler desteklenmiyor; profil listesini elle sağlayın."
                )
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text("\n".join(sorted(links)) + "\n", encoding="utf-8")
            print(f"{len(links)} aday profil yazıldı: {args.output}. Listeyi taramadan önce gözden geçirin.")
        elif args.command == "train":
            from .model import train

            report = train(
                args.data, args.output_dir, args.min_samples, args.test_size, args.seed, args.clusters
            )
            print(
                f"Test accuracy: %{report['test']['accuracy'] * 100:.2f}; macro-F1: {report['test']['macro_f1']:.4f}; ilk 3: %{report['test']['top_3_accuracy'] * 100:.2f}"
            )
            print(f"Model ve ölçümler: {args.output_dir}")
        elif args.command == "predict":
            from .model import load_model, predict

            if args.top_k < 1 or not 0 <= args.threshold <= 1:
                raise ValueError("top-k pozitif, threshold 0 ile 1 arasında olmalı.")
            artifact = load_model(args.model)
            if args.title is not None:
                show_prediction(predict(artifact, args.title, args.top_k, args.threshold))
            else:
                print("Çıkış: q")
                while True:
                    try:
                        title = input("Makale başlığı: ")
                    except EOFError:
                        break
                    if title.strip().lower() == "q":
                        break
                    show_prediction(predict(artifact, title, args.top_k, args.threshold))
    except KeyboardInterrupt:
        print("\nİşlem kullanıcı tarafından durduruldu.", file=sys.stderr)
        return 130
    except (ValueError, OSError, ImportError) as exc:
        print(f"Hata: {exc}", file=sys.stderr)
        return 1
    return 0
