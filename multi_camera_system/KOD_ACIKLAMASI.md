# Multi-Camera Snapshot System - Kod Açıklaması

## 📋 Genel Bakış

Bu sistem, birden fazla IP kameradan otomatik olarak snapshot (anlık görüntü) alan, insan algılama yapan ve görüntüleri S3 Object Storage'a yükleyen bir Python uygulamasıdır. Sistem, PTZ (Pan-Tilt-Zoom) kameraları kontrol ederek önceden tanımlanmış hedeflere yönlendirir ve görüntüleri çeker.

## 🎯 Temel Özellikler

1. **Çoklu Kamera Desteği**: Birden fazla kamerayı aynı anda yönetir
2. **PTZ Kontrolü**: Kameraları önceden tanımlanmış pozisyonlara yönlendirir
3. **İnsan Algılama**: YOLOv8 modeli ile görüntülerde insan tespiti yapar
4. **Otomatik Retry**: İnsan algılanan görüntüleri siler ve tekrar çeker
5. **S3 Entegrasyonu**: Görüntüleri S3 Object Storage'a yükler
6. **Akıllı Dosya Yönetimi**: S3'e yüklenen görüntüler lokal olarak silinir

---

## 📁 Kod Yapısı

### 1. S3 Object Storage Entegrasyonu (Satır 29-100)

#### S3 Ayarları
```python
S3_ENDPOINT_URL = os.getenv("S3_ENDPOINT_URL", "https://161cohesity.carrefoursa.com:3000")
S3_ACCESS_KEY_ID = os.getenv("S3_ACCESS_KEY_ID", "")
S3_SECRET_ACCESS_KEY = os.getenv("S3_SECRET_ACCESS_KEY", "")
S3_BUCKET_NAME = os.getenv("S3_BUCKET_NAME", "Grocery")
```
- S3 bağlantı bilgileri environment variables'dan alınır
- Varsayılan değerler tanımlanmıştır

#### `_ensure_s3_client()` (Satır 41-60)
- **Amaç**: S3 client'ını singleton pattern ile oluşturur
- **Çalışma Mantığı**:
  - İlk çağrıda client oluşturulur
  - Sonraki çağrılarda aynı client döndürülür
  - `boto3` yüklü değilse veya credentials yoksa `None` döner
- **Özellikler**:
  - Self-signed certificate desteği (`verify=False`)
  - Hata durumunda uyarı verir ama programı durdurmaz

#### `_upload_file_to_s3()` (Satır 62-78)
- **Amaç**: Lokal dosyayı S3'e yükler
- **Parametreler**:
  - `local_path`: Yüklenecek dosyanın yolu
  - `s3_key`: S3'teki hedef key (dosya yolu)
  - `content_type`: Dosya tipi (varsayılan: "image/jpeg")
- **Dönüş Değeri**: Başarılıysa S3 key, başarısızsa `None`
- **Özellikler**:
  - Hata durumunda uyarı verir
  - Program akışını durdurmaz

#### `_to_snapshot_s3_key()` (Satır 80-100)
- **Amaç**: Lokal dosya yolunu S3 key formatına çevirir
- **Format**: `snapshots/camera_XXX/YYYY-MM-DD/HH/filename.jpg`
- **Örnek**: 
  - Lokal: `snapshots/camera_001/2025-01-27/17/target_143022.jpg`
  - S3 Key: `snapshots/camera_001/2025-01-27/17/target_143022.jpg`
- **Fallback Mekanizması**: Path çevrilemezse alternatif yöntemler dener

---

### 2. Kamera Konfigürasyon Sınıfları (Satır 103-224)

#### `CameraConfig` Sınıfı (Satır 107-131)
Kamera ayarlarını tutan veri sınıfıdır.

**Özellikler**:
- `camera_id`: Kamera kimliği (örn: "camera_001")
- `name`: Kamera adı
- `host`: Kamera IP adresi
- `username` / `password`: Kimlik doğrulama bilgileri
- `ptz_channel`: PTZ kontrol kanalı (varsayılan: 1)
- `stream_channel`: Video stream kanalı (varsayılan: 101)
- `store_name`: Mağaza adı
- `move_settle_seconds`: PTZ hareket sonrası bekleme süresi (varsayılan: 5 saniye)
- `azimuth_scale` / `elevation_scale` / `zoom_scale`: PTZ koordinat ölçekleri
- `ptz_targets`: PTZ hedefleri (dict formatında)

**Oluşturulan Nesneler**:
- `base_url`: ISAPI endpoint URL'i
- `auth`: HTTP Digest Authentication objesi
- `session`: HTTP session objesi

#### `CameraController` Sınıfı (Satır 134-224)
Kamera ile iletişim kuran kontrol sınıfıdır.

**`_is_ok()` (Satır 142-144)**
- HTTP response'un başarılı olup olmadığını kontrol eder
- 200-299 arası status code'ları başarılı kabul eder

**`ptz_move_absolute()` (Satır 146-169)**
- **Amaç**: PTZ'yi mutlak koordinatlara taşır
- **Parametreler**:
  - `azimuth`: Yatay açı (0-360 derece)
  - `elevation`: Dikey açı
  - `zoom`: Zoom seviyesi
  - `timeout_s`: İstek zaman aşımı
- **Çalışma Mantığı**:
  1. ISAPI endpoint'ine XML formatında PUT isteği gönderir
  2. Koordinatlar scale değerleri ile çarpılır
  3. Başarısız olursa `RuntimeError` fırlatır

**`move_ptz()` (Satır 171-173)**
- `ptz_move_absolute()` için alias fonksiyon

**`take_snapshot()` (Satır 175-220)**
- **Amaç**: Kameradan snapshot alır ve lokal olarak kaydeder
- **Parametreler**:
  - `target_name`: Dosya adı prefix'i
  - `save_dir`: Kayıt dizini
  - `snapshots_root`: Snapshots kök dizini (opsiyonel)
- **Çalışma Mantığı**:
  1. ISAPI streaming endpoint'inden görüntü alır
  2. Tarih/saat bilgisine göre klasör yapısı oluşturur:
     ```
     snapshots/camera_XXX/YYYY-MM-DD/HH/filename.jpg
     ```
  3. Görüntüyü chunk'lar halinde indirir ve kaydeder
  4. Dosya bütünlük kontrolü yapar (5 KB altı dosyalar geçersiz)
  5. Dosya yolunu döndürür
- **Hata Yönetimi**: Başarısız olursa `RuntimeError` fırlatır

**`capture_snapshot()` (Satır 222-224)**
- `take_snapshot()` için alias fonksiyon

---

### 3. Konfigürasyon Yükleme Fonksiyonları (Satır 227-264)

#### `load_camera_configs()` (Satır 231-248)
- **Amaç**: YAML dosyasından kamera konfigürasyonlarını yükler
- **Parametreler**: `config_path` (YAML dosya yolu)
- **Dönüş Değeri**: `Dict[str, CameraConfig]` (kamera_id -> CameraConfig)
- **Çalışma Mantığı**:
  1. Relative path ise script dizinine göre ayarlar
  2. YAML dosyasını okur
  3. Her kamera için `CameraConfig` objesi oluşturur
  4. Dictionary olarak döndürür

#### `get_global_settings()` (Satır 251-264)
- **Amaç**: YAML dosyasından global ayarları yükler
- **Dönüş Değeri**: Global ayarlar dictionary'si
- **Özellikler**: Dosya yoksa boş dict döner

---

### 4. İnsan Algılama (YOLOv8) (Satır 267-347)

#### `get_yolo_model()` (Satır 274-282)
- **Amaç**: YOLOv8 modelini lazy loading ile yükler
- **Çalışma Mantığı**:
  - İlk çağrıda model yüklenir ve global değişkende saklanır
  - Sonraki çağrılarda aynı model döndürülür
- **Model**: YOLOv8s (small versiyonu - daha hızlı)
- **Model Dosyası**: `yolov8s.pt` (otomatik indirilir)

#### `detect_humans_in_image()` (Satır 285-347)
- **Amaç**: Görüntüde insan algılar ve kaplama oranını hesaplar
- **Parametreler**:
  - `image_path`: Analiz edilecek görüntü yolu
  - `min_coverage_ratio`: Minimum kaplama oranı (varsayılan: 0.15 = %15)
- **Dönüş Değeri**: `(has_human, coverage_ratio, person_count)`
  - `has_human`: İnsan algılandı mı? (bool)
  - `coverage_ratio`: İnsanların görüntüyü kaplama oranı (0.0-1.0)
  - `person_count`: Algılanan insan sayısı
- **Çalışma Mantığı**:
  1. YOLOv8 modeli ile görüntüyü analiz eder
  2. Person class ID = 0 (COCO dataset)
  3. Her tespit için bounding box alanını hesaplar
  4. Toplam insan alanını görüntü alanına böler
  5. Kaplama oranı `min_coverage_ratio`'dan büyükse `has_human = True`
- **Hata Yönetimi**: Hata durumunda güvenli tarafta kalır (insan yok kabul eder)

---

### 5. Snapshot Alma ve Retry Mekanizması (Satır 350-467)

#### `capture_snapshot_with_retry()` (Satır 350-467)
- **Amaç**: Snapshot alır, insan algılarsa tekrar çeker, S3'e yükler ve lokal dosyayı siler
- **Parametreler**:
  - `controller`: CameraController objesi
  - `camera_config`: CameraConfig objesi
  - `target_name`: Hedef adı
  - `ptz_coords`: PTZ koordinatları dict'i
  - `save_dir`: Kayıt dizini
  - `snapshots_root`: Snapshots kök dizini
  - `max_retries`: Maksimum deneme sayısı (varsayılan: 5)
  - `min_coverage_ratio`: Minimum kaplama oranı (varsayılan: 0.15)
  - `retry_delay`: Denemeler arası bekleme süresi (varsayılan: 3.0 saniye)

**Çalışma Akışı**:
```
1. PTZ'yi hedef pozisyona taşı (ilk denemede zaten taşınmıştı)
2. Snapshot al ve lokal olarak kaydet
3. İnsan algılama kontrolü yap
4. EĞER insan algılandıysa:
   - Lokal dosyayı sil
   - Maksimum deneme sayısına ulaşılmadıysa tekrar dene
   - Maksimum deneme sayısına ulaşıldıysa None döndür
5. EĞER insan algılanmadıysa:
   - S3'e yükle
   - S3 yükleme başarılıysa lokal dosyayı sil
   - S3 yükleme başarısızsa lokal dosyayı koru
   - Dosya yolunu döndür
```

**Özellikler**:
- Retry mekanizması ile güvenilirlik
- İnsan algılanan görüntüler S3'e yüklenmez
- S3 yükleme başarısız olursa lokal dosya korunur
- Detaylı log mesajları

---

### 6. Ana Snapshot Alma Fonksiyonları (Satır 470-650)

#### `capture_camera_snapshots()` (Satır 474-554)
- **Amaç**: Tek bir kameradan tüm PTZ hedeflerini yakalar
- **Parametreler**:
  - `camera_id`: İşlenecek kamera ID'si
  - `config_path`: Konfigürasyon dosya yolu (varsayılan: 'cameras.yaml')
- **Dönüş Değeri**: İşlem sonuçları dictionary'si

**Çalışma Akışı**:
```
1. Konfigürasyon dosyasını yükle
2. Kamera konfigürasyonunu al
3. CameraController oluştur
4. Snapshots kök dizinini belirle
5. Her PTZ hedefi için:
   a. PTZ'yi hedef pozisyona taşı
   b. Bekleme süresi bekle
   c. capture_snapshot_with_retry() çağır
   d. Sonucu results listesine ekle
6. Özet bilgileri döndür
```

**Dönüş Değeri Yapısı**:
```python
{
    'camera_id': str,
    'total_snapshots': int,
    'snapshots': [
        {
            'target_name': str,
            'snapshot_path': str,
            'ptz_coords': dict,
            'timestamp': str
        },
        ...
    ],
    'timestamp': str
}
```

#### `process_single_configuration()` (Satır 557-603)
- **Amaç**: Tek bir konfigürasyon dosyasındaki tüm kameraları işler
- **Parametreler**: `config_path` (YAML dosya yolu)
- **Dönüş Değeri**: İşlem özeti dictionary'si

**Çalışma Mantığı**:
1. Konfigürasyon dosyasından tüm kameraları yükler
2. Her kamera için `capture_camera_snapshots()` çağırır
3. Sonuçları toplar ve özet oluşturur
4. Hata durumunda diğer kameraları etkilemez

#### `process_all_cameras()` (Satır 606-650)
- **Amaç**: Tüm konfigürasyon dosyalarındaki kameraları işler
- **Parametreler**:
  - `config_path`: Ana konfigürasyon dosyası (varsayılan: 'cameras.yaml')
  - `additional_configs`: Ek konfigürasyon dosyaları listesi
- **Varsayılan Davranış**: `cameras.yaml` ve `cameras_reyon_genel.yaml` birlikte işlenir

**Çalışma Mantığı**:
1. Tüm konfigürasyon dosyalarını toplar
2. Her konfigürasyon için `process_single_configuration()` çağırır
3. Sonuçları birleştirir
4. Genel özet oluşturur

---

### 7. Ana Program (Satır 653-712)

#### `main()` (Satır 657-708)
- **Amaç**: Programın giriş noktası
- **Çalışma Akışı**:
  1. Başlık ve bilgilendirme mesajları yazdırır
  2. Başlangıç zamanını kaydeder
  3. `process_all_cameras()` çağırır
  4. İşlem süresini hesaplar
  5. Detaylı rapor yazdırır:
     - Toplam kamera sayısı
     - Toplam snapshot sayısı
     - İşlem süresi
     - Her konfigürasyon için detaylar
     - Her kamera için snapshot sayısı
  6. Snapshot klasörü bilgisini gösterir

**Hata Yönetimi**:
- `KeyboardInterrupt`: Kullanıcı iptal ederse uygun mesaj gösterir
- Diğer hatalar: Hata mesajı ve stack trace gösterir

---

## 🔄 Çalışma Akışı (Genel)

```
1. main() çağrılır
   ↓
2. process_all_cameras() çağrılır
   ↓
3. Her konfigürasyon dosyası için:
   process_single_configuration() çağrılır
   ↓
4. Her kamera için:
   capture_camera_snapshots() çağrılır
   ↓
5. Her PTZ hedefi için:
   a. PTZ hareket ettirilir
   b. capture_snapshot_with_retry() çağrılır
      ↓
   c. take_snapshot() ile görüntü alınır
      ↓
   d. detect_humans_in_image() ile insan kontrolü yapılır
      ↓
   e. İnsan yoksa:
      - _upload_file_to_s3() ile S3'e yüklenir
      - Başarılıysa lokal dosya silinir
      - Başarısızsa lokal dosya korunur
   f. İnsan varsa:
      - Lokal dosya silinir
      - Retry yapılır (max_retries kadar)
```

---

## 📂 Dosya Yapısı

### Lokal Dosya Yapısı
```
snapshots/
└── camera_001/
    └── 2025-01-27/
        └── 17/
            ├── target1_143022.jpg
            ├── target2_143045.jpg
            └── ...
```

### S3 Object Storage Yapısı
```
s3://Grocery/
└── snapshots/
    └── camera_001/
        └── 2025-01-27/
            └── 17/
                ├── target1_143022.jpg
                ├── target2_143045.jpg
                └── ...
```

**Not**: S3'e başarıyla yüklenen görüntüler lokal olarak silinir.

---

## ⚙️ Konfigürasyon Dosyası Yapısı

### YAML Formatı Örneği
```yaml
global_settings:
  snapshots_root: "snapshots"

cameras:
  camera_001:
    name: "Kamera 1"
    host: "192.168.1.100"
    username: "admin"
    password: "password123"
    ptz_channel: 1
    stream_channel: 101
    store_name: "Mağaza A"
    move_settle_seconds: 5
    azimuth_scale: 10
    elevation_scale: 10
    zoom_scale: 10
    ptz_targets:
      target1:
        azimuth: 0.0
        elevation: 0.0
        zoom: 0.5
      target2:
        azimuth: 45.0
        elevation: -10.0
        zoom: 0.7
```

---

## 🔐 Environment Variables

S3 entegrasyonu için gerekli environment variables:

```bash
S3_ENDPOINT_URL=https://161cohesity.carrefoursa.com:3000
S3_ACCESS_KEY_ID=your_access_key
S3_SECRET_ACCESS_KEY=your_secret_key
S3_BUCKET_NAME=Grocery
```

---

## 📊 Özellikler ve Limitler

### Özellikler
✅ Çoklu kamera desteği
✅ PTZ otomatik kontrolü
✅ İnsan algılama ve filtreleme
✅ Otomatik retry mekanizması
✅ S3 Object Storage entegrasyonu
✅ Akıllı dosya yönetimi
✅ Detaylı loglama
✅ Hata toleransı

### Limitler
- Maksimum retry sayısı: 5 (ayarlanabilir)
- Minimum dosya boyutu: 5 KB
- İnsan algılama eşiği: %15 kaplama oranı (ayarlanabilir)
- PTZ hareket sonrası bekleme: 5 saniye (ayarlanabilir)

---

## 🚀 Kullanım

### Temel Kullanım
```python
from camera_snapshot_system import main

# Tüm kameraları işle
main()
```

### Tek Kamera İşleme
```python
from camera_snapshot_system import capture_camera_snapshots

result = capture_camera_snapshots("camera_001")
print(f"Toplam snapshot: {result['total_snapshots']}")
```

### Özel Konfigürasyon
```python
from camera_snapshot_system import process_all_cameras

result = process_all_cameras(
    config_path='cameras.yaml',
    additional_configs=['cameras_extra.yaml']
)
```

---

## 🐛 Hata Yönetimi

Sistem, hata durumlarında programı durdurmaz:
- **S3 bağlantı hatası**: Uyarı verir, lokal dosya korunur
- **Kamera bağlantı hatası**: O kamera atlanır, diğerleri devam eder
- **İnsan algılama hatası**: Güvenli tarafta kalır (insan yok kabul eder)
- **Dosya yazma hatası**: Uyarı verir, işlem devam eder

---

## 📝 Log Mesajları

Sistem detaylı log mesajları üretir:
- `[✓]`: Başarılı işlem
- `[UYARI]`: Uyarı mesajı
- `[HATA]`: Hata mesajı
- `[İNSAN ALGILANDI]`: İnsan tespit edildi
- `[SİLİNDİ]`: Dosya silindi
- `[RETRY]`: Tekrar deneme

---

## 🔧 Geliştirme Notları

1. **YOLOv8 Modeli**: İlk kullanımda otomatik indirilir
2. **S3 Client**: Singleton pattern ile optimize edilmiştir
3. **Path Yönetimi**: `pathlib.Path` kullanılarak cross-platform uyumluluk sağlanmıştır
4. **Hata Toleransı**: Her seviyede hata yakalama mekanizması vardır
5. **Performans**: Lazy loading ve singleton pattern ile optimize edilmiştir

---

## 📚 Bağımlılıklar

- `requests`: HTTP istekleri için
- `PIL` (Pillow): Görüntü işleme için
- `ultralytics`: YOLOv8 modeli için
- `yaml`: Konfigürasyon dosyası okuma için
- `boto3`: S3 Object Storage için (opsiyonel)
- `numpy`: Sayısal işlemler için

---

## 📄 Lisans ve Notlar

Bu kod, Carrefoursa reyon kamera entegrasyonu için geliştirilmiştir.
Kod içinde detaylı açıklamalar ve docstring'ler bulunmaktadır.

