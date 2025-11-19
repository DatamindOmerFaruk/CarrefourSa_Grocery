# Batch Processor Dokümantasyonu

## 📋 Batch İşlemi Ne Yapıyor?

Batch processor, S3 Object Storage'dan genel reyon görüntülerini alıp, bunları AI API'lere göndererek analiz sonuçlarını PostgreSQL veritabanına kaydeden bir sistemdir.

## 🔄 İşlem Akışı

### 1. **Başlangıç**
- `.env` dosyasından konfigürasyon yüklenir (S3, PostgreSQL, API ayarları)
- S3 Object Storage'a bağlanılır
- PostgreSQL veritabanına bağlanılır
- Tablolar kontrol edilir/oluşturulur (DDL çalıştırılır)
- API sağlık kontrolü yapılır

### 2. **Görsel Listeleme**
- S3'ten `snapshots/genel_gorunum/` klasöründeki görseller listelenir
- Her görsel için S3 URL oluşturulur
- Görseller batch'ler halinde işlenir (varsayılan: 10'ar 10'ar)

### 3. **İki Mod Seçeneği**

#### **Mod 1: Tam Analiz (Content + Stock + Evaluation)**
1. **Content API** → Görüntüdeki kasa düzenini analiz eder
   - Satır/sütun sayısı
   - Her satırdaki ürünler (ana ürün, yan ürünler)
   - Konum bilgileri
   - → `analyze_row` tablosuna kaydedilir

2. **Stock API** → Reyon doluluk durumunu analiz eder
   - Her reyonun durumu (dolu, normal, kritik, boş)
   - Doluluk seviyeleri
   - Aciliyet durumu
   - → `analyze_stock_row` tablosuna kaydedilir

3. **Evaluation API** → Problem çıktılarını analiz eder
   - Genel skor
   - Tespit edilen hatalar (her hata için ayrı satır)
   - Olumlu yerleşimler
   - Genel öneriler
   - → `analyze_evaluation_row` tablosuna kaydedilir

#### **Mod 2: Stock + Evaluation Analizi (Hızlı)**
1. **Stock API** → Reyon doluluk durumunu analiz eder
   - → `analyze_stock_row` tablosuna kaydedilir

2. **Evaluation API** → Problem çıktılarını analiz eder
   - → `analyze_evaluation_row` tablosuna kaydedilir

### 4. **Veritabanı Kayıtları**

#### **analyze_row** (Content Analizi)
- `source_url`: S3 görsel URL'i
- `ts`: Kayıt zamanı
- `row_index`: Satır indeksi (NOT NULL)
- `konum`: Ürün konumu (NOT NULL)
- `ana_urun`: Ana ürün adı (NOT NULL)
- `yan_urunler`: Yan ürünler
- `satir_sayisi`, `sutun_sayisi`, `toplam_kasa`: Grid bilgileri
- `raw`: Tüm API yanıtı (JSONB, NOT NULL)

#### **analyze_stock_row** (Stock Analizi)
- `source_url`: S3 görsel URL'i
- `ts`: Kayıt zamanı
- `reyon_id`: Reyon ID (NOT NULL)
- `doluluk`: Doluluk oranı (NUMERIC(6,4))
- `durum`: Durum özeti (Dolu:X Normal:Y Kritik:Z Boş:W)
- `aciliyet`: Aciliyet seviyesi (düşük/orta/yüksek)
- `kasa_gorunurlugu`: Kasa görünürlüğü (boolean)
- `doluluk_seviyeleri`: Metin formatında doluluk özeti (NOT NULL)
- `raw`: Tüm API yanıtı (JSONB, NOT NULL)

#### **analyze_evaluation_row** (Evaluation Analizi)
- `source_url`: S3 görsel URL'i
- `ts`: Kayıt zamanı
- `genel_skor`: Genel değerlendirme skoru (NUMERIC(6,3))
- `toplam_hata`, `kritik_hata`, `uyari`: Hata istatistikleri
- `analiz_modu`: Analiz modu (detayli_analiz/direkt_analiz)
- `hata_tipi`: Hata tipi (varsa)
- `konum1`, `urun1`, `konum2`, `urun2`: Hata konumları ve ürünleri
- `problem`: Problem açıklaması
- `oneri`: Öneri
- `olumlu_yerlesimler`: Olumlu yerleşimler (JSONB, NOT NULL)
- `genel_oneriler`: Genel öneriler (JSONB, NOT NULL)
- `raw`: Tüm API yanıtı (JSONB, NOT NULL)

**Not:** Her hata için ayrı satır kaydedilir. Hata yoksa tek satır kaydedilir.

### 5. **Hata Yönetimi**
- API çağrıları 3 kez denenir (retry)
- Başarısız görseller log'a yazılır
- Başarılı/başarısız istatistikleri tutulur
- Her batch arasında bekleme süresi var (rate limiting)

## 📊 Tablo Yapıları

Tüm tablolarda:
- `id`: BIGSERIAL PRIMARY KEY
- `source_url`: TEXT NOT NULL (S3 görsel URL'i)
- `ts`: TIMESTAMPTZ NOT NULL DEFAULT NOW() (kayıt zamanı)
- `raw`: JSONB NOT NULL (tüm API yanıtı)

### Index'ler
- `source_url` üzerinde index (hızlı sorgulama için)
- `ts` üzerinde index (zaman bazlı sorgular için)
- İlgili alanlar üzerinde index'ler (ör: `ana_urun`, `durum`, `hata_tipi`)

## 🔧 Konfigürasyon

`.env` dosyasından alınan ayarlar:
- `S3_ENDPOINT_URL`: S3 endpoint URL'i
- `S3_ACCESS_KEY_ID`: S3 access key
- `S3_SECRET_ACCESS_KEY`: S3 secret key
- `S3_BUCKET_NAME`: S3 bucket adı
- `POSTGRES_HOST`: PostgreSQL host (45.84.18.76)
- `POSTGRES_PORT`: PostgreSQL port (5432)
- `POSTGRES_DB`: PostgreSQL database (postgres)
- `POSTGRES_USER`: PostgreSQL kullanıcı adı
- `POSTGRES_PASSWORD`: PostgreSQL şifresi
- `API_BASE_URL`: API base URL (http://localhost:8000)
- `BATCH_SIZE`: Batch boyutu (varsayılan: 10)
- `RETRY_COUNT`: Retry sayısı (varsayılan: 3)
- `REQUEST_DELAY`: Request arası bekleme (varsayılan: 1.0 saniye)

## 📝 Log Mesajları

- `✅ VERİTABANI: ... kaydedildi` → Başarılı kayıt
- `[STOCK ✅ | EVAL ✅]` → Her iki analiz başarılı
- `[STOCK FAIL]` → Stock analizi başarısız
- `ERROR` → Hata mesajları

## 🚀 Kullanım

```bash
cd doluluk&reyonsıralaması/manav_analiz
python batch_processor.py
```

Mod seçimi:
- `1`: Tam Analiz (Content + Stock + Evaluation)
- `2`: Stock + Evaluation Analizi (Hızlı)

