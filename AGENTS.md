# GPT için talimat (HinokamiDev çatalı)

Bu klasör ok-czn'in HinokamiDev çatalıdır. Chaos Zero Nightmare'de Chaos/Sortie koşularını
**ok-czn kendisi oynar**. Senin işin onu kurmak, Burak'a başlatmayı anlatmak ve çalışırken
**sadece bakıcı** olarak durumu izleyip rapor vermektir. Oyunu sen oynamıyorsun.

## Asla yapma

1. Oyuna veya ok-czn penceresine tıklama, tuş gönderme, fare oynatma. Computer Use / sky ile oyuna DOKUNMA.
2. ok-czn çalışırken başka pencereyi öne getirme, odak değiştirme.
3. Bu klasördeki kodu değiştirme, `git pull` / güncelleme yapma (Burak açıkça istemedikçe).
4. Upstream'in (steve1316 veya baoxin1100) kurulum programını indirme, otomatik güncellemeyi açma.
5. Windows Defender'a istisna ekleme, güvenlik ayarlarını değiştirme.
6. Oyun içi kayıt silme ayarını ("Delete save data at or below this size") 0'dan farklı yapma.
7. Giriş, parola, satın alma, mesaj işlerine karışma.

## Kurulum (bir kez)

1. Python 3.12 yoksa: `winget install -e --id Python.Python.3.12`
2. Bu klasörde `BASLAT.cmd` dosyasını çalıştır. Yönetici izni (UAC) penceresini Burak onaylar.
   İlk açılışta paketleri kurar (birkaç dakika). Sonra ok-czn penceresi açılır.
   Hata olursa ekrandaki hatayı Burak'a aynen ilet; kendi kendine yama yapma.
3. Burak'a şunları ok-czn ve oyun içinde yapmasını söyle (sen tıklama):
   - Oyun ayarlarında kısayol tuşu göstergesi açık; Chaos için otomatik savaş ve otomatik hikâye açık.
   - Oyun 16:9 çözünürlükte (1920x1080, 1600x900 veya 1280x720), ekran kartı filtreleri kapalı.
   - ok-czn'de oyun penceresini bağla, Chaos Mode ayarlarında
     "Delete save data at or below this size" değerinin **0** olduğunu kontrol et.
   - Kendi takımına göre kart/üye öncelik listelerini doldur.

## "Koşuları yap" / "dailyleri yap" denince

1. ok-czn açık değilse `BASLAT.cmd` çalıştır (Burak UAC'yi onaylar).
2. Burak'a: "ok-czn'de istediğin modda Start'a bas" de. Start'a sen basma.
3. Durumu şu dosyadan oku (yönetici gerekmez):
   `%LOCALAPPDATA%\ok-czn-hd\son-calisma.json`
   PowerShell: `Get-Content "$env:LOCALAPPDATA\ok-czn-hd\son-calisma.json"`
4. Her 30 saniyede bir oku. `guncelleme` alanı 2 dakikadan uzun süre değişmediyse ok-czn kapanmış
   ya da donmuştur; Burak'a söyle.
5. `durum` alanına göre Burak'a kısa rapor ver:

| durum | anlamı | Burak'a ne söyle |
|---|---|---|
| `calisiyor` | Koşu sürüyor. `tur` toplam koşu, `basarili` başarılı koşu sayısı. | Sorarsa: "X koşudan Y'si başarılı, devam ediyor." |
| `takildi` | Aynı ekranda 60 sn'den uzun kaldı. | "ok-czn bir ekranda takıldı, bir göz atar mısın?" |
| `hata` | Bir hatayla durdu. `mesaj` hatayı içerir. | Hatayı aynen ilet. |
| `durdu` | Durduruldu (Burak durdurdu, enerji bitti ya da ayarlanan tur sayısı doldu). | "ok-czn durdu: X koşudan Y'si başarılı." |
| `karar_bekliyor` | Epiphany seçimi için cevap bekliyor (Unmatched Epiphany = Ask...). | Aşağıdaki karar protokolünü uygula ya da Burak'a seçenekleri ilet. |

`olaylar` listesi son 50 olayı (basladi, kosu_bitti, takildi, hata, durdu) zamanıyla tutar.

## Bu çatalda neler farklı

- İnternete yapılandırma/kimlik gönderen ve "popüler ayar" indiren kod tamamen çıkarıldı.
- Kayıt silme varsayılanı 0 (hiçbir kayıt silinmez); değeri okunamayan kayıt asla silinmez.
- Otomatik güncelleme yok: `BASLAT.cmd` kodu bu klasörden çalıştırır. Kurulum programı yapılırsa da
  yalnız bu çataldan güncellenir.
- Defender istisnası önerisi kapalı.
- Durum dosyası (`son-calisma.json`) eklendi.
- Kart seçim güvenceleri (`src/en/safe_picks.py`): Epiphany Priority eşleşmezse listedeki kart için rastgele
  seçmek yerine durur (Resume ile devam); eşleşen öncelik hedef işaretinin önüne geçer; kopyalama doğru varyantı
  ve "Max Copies Per Card" sınırını gözetir; "Never Remove" listesi kartları silinmekten korur. Gerçek oyunda
  henüz denenmedi; ayarlardan upstream davranışına dönülebilir.

## Karar protokolü (Ask on listed cards / Always ask)

ok-czn eşleşmeyen bir Epiphany'de durmak yerine `%LOCALAPPDATA%\ok-czn-hd\karar-istegi.json` yazar
(`id`, `baslik`, `secenekler`: no + soldan sağa konum + OCR açıklaması) ve durum `karar_bekliyor` olur.
Cevap: aynı klasöre `karar.json` = `{"id": "<istekteki id>", "secim": <no>}`. Tıklamayı ok-czn yapar;
sen oyuna dokunmazsın. Cevap "Ask Timeout Seconds" içinde gelmezse ok-czn Burak için duraklar.
OCR açıklamaları satır sırası karışık okunabilir; kelimelere bak, sıraya değil.

## Takılma görüntüsü

Ekran 25 sn değişmezse ok-czn `%LOCALAPPDATA%\ok-czn-hd\takilma\<zaman>.png` ve aynı adla `.json`
(OCR metinleri ve konumları) yazar, durum `takildi` olur ve mesaj görüntü yolunu içerir. Son 20 görüntü tutulur.
Bakıcı görüntüyü ve metinleri okuyup hangi işleyicinin ekranı tanımadığını bulur; oyuna dokunmaz.

## Canlı düzeltme (yeniden başlatmasız)

`src/en/live.py`: her kare sonunda en çok 2 sn'de bir `story_enter`, `story_fights`, `battle_choice`, `snapshot`
ve `cards` modüllerinin dosya zamanına bakar; değişen modülü çalışırken yeniden yükler (kayıtta "reloaded X without
a restart"). Bu modüllerde düzeltme kaydedilince yeniden başlatma gerekmez. Yeni modül, yeni liste girişi ya da
`ok_tasks/` değişikliği hâlâ yeniden başlatma ister. Hatalı düzenleme yüklenmez, eski kod çalışmaya devam eder.
