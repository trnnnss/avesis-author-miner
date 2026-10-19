# Teknik notlar

## Sorumluluklar

`data.py` yalnızca dosya ve ortak veri şemasıyla ilgilenir. `scraping.py` HTTP oturumu, robots politikası, bekleme ve HTML adaptörünü kapsar. `model.py` internete çıkmaz; eğitim ve tahmin için aynı normalizasyonu kullanır. `cli.py` kullanıcı girdisini bu işlevlere bağlar. Modülleri import etmek tarama, eğitim veya `input()` başlatmaz.

## Veri sözleşmesi

Gerekli alanlar `title` ve `author`, isteğe bağlı alanlar `authors`, `source_url` ve kullanıcıya ait ek sütunlardır. Kaynak dosya değişmeden kalır. Tarama çıktısına yeni kayıtlar eklenirken eski sütunlar korunur; eski üç sütunlu satırlarla yeni iki sütunlu satırların aynı listeye konmasından kaynaklanan hata giderilmiştir. Aynı normalize başlıkta farklı ilk yazarlar ham çıktıda tutulur, eğitimde dışlanır. Temizleme sayaçları raporlanır.

## Değerlendirme sınırı

Temizleme ve minimum sınıf kapsamı, deneyin hangi veriyi kapsadığını tanımlar. Sonra katmanlı ayrı test bölümü ayrılır. TF-IDF öğrenimi, model seçimi ve olasılık kalibrasyonu yalnızca eğitim bölümünde yapılır. Aday seçimi macro-F1 ile yapılır; test skoru aday seçiminde kullanılmaz. Kalibrasyon sırasında da TF-IDF her kat için yeniden öğrenilir. Bunun için `CalibratedClassifierCV` içine bütün `Pipeline` yerleştirilir.

Son test skoru kaydedildikten sonra dağıtım modeli bütün uygun veriyle yeniden eğitilir. Model dosyası bu son modeli, ölçüm raporu ise ayrı test deneyini içerir. Kalibrasyon `ensemble=False` kullanır; böylece çıkarımda tek özellik çıkarıcı ve tek sınıflandırıcı tutulur. KMeans aynı son özellik uzayını kullanır; etiket tahminini etkilemez.

Mevcut kelime SVM karşılaştırması aynı temizlenmiş veri, aynı bölme ve aynı kalibrasyon yordamıyla çalışır. Önceki çevrimiçi çevirili, sızıntılı betiğin skoruymuş gibi raporlanmaz. Minimum örnek eşiği daha yüksek bir skor uğruna test sonucuna göre değiştirilmemelidir.

## Yeni site adaptörü

Yeni kaynağın okuyucusu, `title`, `author`, mümkünse `authors` ve `source_url` üreten satırlar döndürmelidir. AVESİS seçicilerini farklı siteler için giderek karmaşıklaştırmak yerine ayrı okuyucu ekleyin. Ağ isteklerini tek bir sınırlandırılmış istemciden yapın; ayrıştırıcı testlerinde kaydedilmiş küçük HTML örnekleri kullanın. Kullanıcıya eksik sonuçları açıkça bildirin.

## Kayıt ve sürümler

Veri çıktısı aynı klasörde geçici dosyaya yazılıp değiştirilir. Bu bir tam işlem veritabanı değildir; eşzamanlı iki tarayıcıyı aynı çıktı dosyasına yönlendirmeyin. Model kaydı da geçici dosya üzerinden yenilenir; model ve JSON raporu iki ayrı dosyadır. Ayrı deney klasörleri kullanmak sonuçların karışmasını engeller.

Modelin şema sürümü ve scikit-learn sürümü doğrulanır. joblib güvenilmeyen dosyalar için kullanılmamalıdır. Yeni bir kütüphane sürümüne geçildiğinde model yeniden eğitilmelidir. Testler ve sürüm kaydı platformlar arası mutlak bit eşitliği garantisi vermez.
