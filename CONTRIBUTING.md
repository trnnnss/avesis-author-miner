# Katkıda bulunma

Önce README'deki kurulumu yapın; geliştirme araçları için `python -m pip install -e ".[dev]"` kullanın.

1. Sorunu veya öneriyi bir issue ile açıklayın. Hata için küçük bir veri örneği ve tekrarlama komutu ekleyin.
2. Kendi dalınızda odaklı bir değişiklik yapın.
3. `ruff check .` ve `python -m pytest -q` çalıştırın. Ağ gerektiren testleri birim testlerine eklemeyin; HTML örnekleri kullanın.
4. Kullanıcı davranışı değişiyorsa README'yi güncelleyin ve pull request açın.

Model iyileştirmelerinde yalnızca accuracy artışını raporlamak yeterli değildir. Aynı veri temizliği ve bölme üzerinde macro-F1, ilk üç doğruluğu ve sınıf kapsamını da raporlayın. Test kümesine göre parametre seçmeyin. Yeni veri kaynakları için AVESİS HTML adaptöründen ayrı bir okuyucu ve test ekleyin.

Kod MIT lisansı ile paylaşılır; ayrıntılar için [LICENSE](LICENSE) dosyasına bakın. Katkıların da bu lisans altında sunulması beklenir. Veri kaynaklarının kullanım koşulları ayrıca geçerlidir.
