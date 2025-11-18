# Linux Sunucu Deployment Rehberi

Bu rehber, tüm projeyi Linux sunucuda çalıştırmak için gerekli adımları içerir.

## 📋 İçindekiler

1. [Sistem Gereksinimleri](#sistem-gereksinimleri)
2. [Kurulum Adımları](#kurulum-adımları)
3. [Konfigürasyon](#konfigürasyon)
4. [Servisler Hakkında](#servisler-hakkında)
5. [Servisleri Başlatma](#servisleri-başlatma)
6. [İzleme ve Loglar](#izleme-ve-loglar)
7. [Sorun Giderme](#sorun-giderme)
8. [Hızlı Başlangıç Özeti](#hızlı-başlangıç-özeti)

---

## 🖥️ Sistem Gereksinimleri

### Minimum Gereksinimler

- **OS**: Ubuntu 20.04+ / Debian 11+ / CentOS 8+ / RHEL 8+
- **Python**: 3.10 veya üzeri
- **RAM**: 8 GB (16 GB önerilir - YOLO modeli için)
- **Disk**: 50 GB boş alan
- **GPU**: Opsiyonel (CUDA destekli GPU varsa YOLO daha hızlı çalışır)

### Gerekli Sistem Paketleri

```bash
sudo apt-get update
sudo apt-get install -y \
    python3 \
    python3-pip \
    python3-venv \
    git \
    build-essential \
    libpq-dev \
    postgresql-client \
    curl \
    wget
```

---

## 📦 Kurulum Adımları

### 1. Projeyi Sunucuya Kopyalama

```bash
# Sunucuya SSH ile bağlan
ssh user@your-server-ip

# Proje dizini oluştur
sudo mkdir -p /data/carrefoursa-kamera/CarrefourSa_Grocery
sudo chown $USER:$USER /data/carrefoursa-kamera
cd /data/carrefoursa-kamera/CarrefourSa_Grocery

# Projeyi kopyala (GitHub'dan veya SCP ile)
# Örnek: Git kullanıyorsanız
git clone <repository-url> .

# Veya SCP ile Windows'tan kopyalama:
# scp -r "C:\Users\test\Desktop\Carrefoursa\reyon\Kamera Entegrasyon" user@server:/data/carrefoursa-kamera/CarrefourSa_Grocery
```

### 2. Python Virtual Environment Oluşturma

```bash
cd /data/carrefoursa-kamera/CarrefourSa_Grocery

# Virtual environment oluştur
python3 -m venv venv

# Virtual environment'ı aktif et
source venv/bin/activate

# Pip'i güncelle
pip install --upgrade pip setuptools wheel
```

**Virtual Environment Nedir?**

Virtual environment, projeye özel Python paketlerini yönetmek için kullanılan izole bir ortamdır. Her proje kendi bağımlılıklarını yönetir, sistem Python'u etkilenmez. Bu sayede farklı projeler farklı paket sürümleri kullanabilir ve çakışmalar önlenir.

### 3. Bağımlılıkları Yükleme

```bash
# Ana requirements dosyasını yükle
pip install -r requirements.txt

# Eğer requirements.txt yoksa, tüm bağımlılıkları manuel yükle:
pip install \
    requests>=2.32.0 \
    Pillow>=10.0.0 \
    numpy>=1.24.0 \
    opencv-python>=4.8.0 \
    PyYAML>=6.0.1 \
    ultralytics>=8.0.0 \
    torch>=2.0.0 \
    facenet-pytorch \
    fastapi==0.104.1 \
    uvicorn==0.24.0 \
    python-multipart==0.0.6 \
    python-dotenv==1.0.0 \
    boto3>=1.34.0 \
    psycopg2-binary>=2.9.0,<3.0.0 \
    azure-storage-blob==12.19.0 \
    openai>=1.30.0
```

### 4. Model Dosyalarını Kontrol Etme

```bash
# YOLO model dosyalarının varlığını kontrol et
ls -lh best.pt

# Eğer yoksa, YOLO otomatik indirecek (ilk çalıştırmada)
```

---

## ⚙️ Konfigürasyon

### 1. Environment Variables (.env dosyası)

```bash
# .env dosyası oluştur
nano /data/carrefoursa-kamera/CarrefourSa_Grocery/.env
```

`.env` dosyası içeriği:

```bash
# S3 Object Storage Ayarları
S3_ENDPOINT_URL=https://161cohesity.carrefoursa.com:3000
S3_ACCESS_KEY_ID=sWxdTl3ERx7myBE1qpW06_haVvuhATcdsmBbqaWkXYU
S3_SECRET_ACCESS_KEY=Ti9Fonk3wYyG5PMx5LaGUmlcVyCuqsE5BLVV5vv8PU0
S3_BUCKET_NAME=Grocery

# PostgreSQL Veritabanı
PG_HOST=45.84.18.76
PG_PORT=5432
PG_USER=grocerryadmin
PG_PASSWORD=a08Iyr95vLHTYY
PG_DATABASE=grocerryadmin
PG_DSN=postgresql://grocerryadmin:a08Iyr95vLHTYY@45.84.18.76:5432/grocerryadmin

# Azure OpenAI (LLM için)
AZURE_OPENAI_ENDPOINT=https://your-endpoint.openai.azure.com/
AZURE_OPENAI_API_KEY=your-api-key
AZURE_OPENAI_DEPLOYMENT=gpt-4.1
AZURE_API_VERSION=2024-06-01

# API Ayarları (Batch Processor için)
API_BASE_URL=http://localhost:8000
BATCH_SIZE=10
RETRY_COUNT=3
REQUEST_DELAY=1.0

# Diğer Ayarlar
MIN_CONF_ROTTEN=0.85
COLLAGE_FONT=
TEST_MODE=false
```

**Not**: Azure Storage ayarları artık kullanılmıyor (S3'e geçildi), ancak eski kodlarla uyumluluk için `.env` dosyasında bırakılabilir.

### 2. Dosya İzinlerini Ayarlama

```bash
# Gerekli dizinleri oluştur
mkdir -p snapshots crops logs

# İzinleri ayarla
chmod 755 /data/carrefoursa-kamera/CarrefourSa_Grocery
chmod 644 /data/carrefoursa-kamera/CarrefourSa_Grocery/.env
```

### 3. Kamera Konfigürasyon Dosyalarını Kontrol Etme

```bash
# Kamera konfigürasyon dosyalarını kontrol et
ls -lh multi_camera_system/cameras.yaml
ls -lh multi_camera_system/cameras_reyon_genel.yaml

# İçeriklerini kontrol et ve gerekirse düzenle
nano multi_camera_system/cameras.yaml
```

### 4. Sistem Saatini Ayarlama

**ÖNEMLİ**: Sistem saati yanlışsa, fotoğrafların tarih/saat bilgileri ve klasör yapısı yanlış olur.

```bash
# Mevcut sistem saatini kontrol et
date
timedatectl

# Timezone'u Türkiye saati (Europe/Istanbul) olarak ayarla
sudo timedatectl set-timezone Europe/Istanbul

# NTP ile senkronize et (otomatik saat düzeltme)
sudo timedatectl set-ntp true

# Saati kontrol et
date
```

**Not**: Kod zaten Türkiye saatini (UTC+3) kullanacak şekilde yapılandırılmıştır. Sistem saati yanlış olsa bile, kod UTC'den Türkiye saatine çevirir. Ancak sistem saatini düzeltmek daha iyidir çünkü cron job'lar doğru saatte çalışır.

---

## 🚀 Servisler Hakkında

Sistemde 4 ana servis bulunmaktadır:

### 1. **Camera Snapshot System** (`multi_camera_system/camera_snapshot_system.py`)

- **Görevi**: PTZ kameralardan görüntü alır, YOLO ile insan tespiti yapar, geçerli görüntüleri S3 Object Storage'a yükler
- **Çalışma Şekli**: Cron job ile saatlik çalışır (09:00-21:00 arası, her saat başı)
- **Özellikler**:
  - Çoklu kamera desteği
  - İnsan tespiti ile kalite kontrolü
  - Otomatik retry mekanizması
  - S3'e otomatik yükleme (bucket: `Grocery`, prefix: `snapshots/`)
  - Lokal dosyaları S3'e yüklendikten sonra silme
  - Türkiye saati (UTC+3) kullanımı

### 2. **Manav Analiz API** (`doluluk&reyonsıralaması/manav_analiz/main.py`)

- **Görevi**: FastAPI tabanlı REST API servisi. Görüntü analizi için endpoint'ler sağlar
- **Çalışma Şekli**: Systemd service olarak sürekli çalışır (7/24)
- **Özellikler**:
  - Content analizi endpoint'i
  - Stock analizi endpoint'i
  - Evaluation endpoint'i
  - Health check endpoint'i
  - Port: 8000
- **Not**: Batch Processor bu API'yi kullanıyorsa gerekli

### 3. **Batch Processor** (`doluluk&reyonsıralaması/manav_analiz/batch_processor.py`)

- **Görevi**: S3 Object Storage'dan görüntüleri alır, Manav Analiz API'ye gönderir, sonuçları PostgreSQL'e kaydeder
- **Çalışma Şekli**: Cron job ile saatlik çalışır (09:30-21:30 arası, camera-snapshot'tan 30 dakika sonra)
- **Özellikler**:
  - S3'ten görüntü listeleme (`snapshots/` prefix'i altında)
  - Batch işleme (toplu analiz)
  - API çağrıları (Content, Stock, Evaluation)
  - PostgreSQL'e sonuç kaydetme
  - Retry mekanizması
  - İki mod: Tam analiz veya sadece stock analizi

### 4. **PTZ Analysis Service** (3 ayrı script)

- **Görevi**: S3'ten snapshot'ları alır, YOLO ile detection yapar, crop'lar oluşturur, collage'lar hazırlar, LLM ile çürük tespiti yapar ve sonuçları PostgreSQL'e kaydeder
- **Çalışma Şekli**: Cron job ile saatlik çalışır (09:30-21:30 arası, camera-snapshot'tan 30 dakika sonra)
- **Script'ler**:
  1. **`ptz_face_blur.py`** (opsiyonel): Yüzlerin blur'lanması - S3'ten snapshot'ları alır, yüzleri tespit edip blur'lar, tekrar S3'e yükler
  2. **`ptz_yolo_llm_analysis.py`**: YOLO detection ve LLM analizi - S3'ten snapshot'ları alır, YOLOv12 ile detection yapar, crop'lar oluşturur, collage'lar hazırlar, Azure OpenAI ile çürük tespiti yapar, sonuçları `.llm.json` dosyalarına kaydeder ve S3'e yükler
  3. **`ptz_db_writer.py`**: Veritabanına yazma - S3'ten `.llm.json` dosyalarını okur ve PostgreSQL veritabanına sonuçları yazar
- **Özellikler**:
  - 3 aşamalı pipeline (yüz blur → YOLO+LLM analizi → DB yazma)
  - S3'ten snapshot indirme
  - YOLO ile meyve/sebze detection ve cropping
  - Collage oluşturma (batch'ler halinde)
  - Azure OpenAI (GPT-4.1) ile çürük tespiti
  - PostgreSQL'e sonuç kaydetme (llm_runs, llm_items tablolarına)
  - S3'e crop, collage ve rapor yükleme
  - Script'ler sırayla çalışır (bir hata olursa işlem durdurulur)

### Servis Koordinasyonu ve Zamanlama

Servisler aşağıdaki akışa göre çalışır:

```
[09:00] → Camera Snapshot System (Görüntüleri S3'e yükler)
[09:30] → Batch Processor (S3'ten yeni görüntüleri alır, API'ye gönderir, DB'ye kaydeder)
[09:30] → PTZ Analysis Service (S3'ten yeni görüntüleri alır, YOLO+LLM analizi yapar, DB'ye kaydeder)

[10:00] → Camera Snapshot System
[10:30] → Batch Processor
[10:30] → PTZ Analysis Service
...
[21:00] → Camera Snapshot System (Son çalışma)
[21:30] → Batch Processor (Son çalışma)
[21:30] → PTZ Analysis Service (Son çalışma)

Manav API → 7/24 sürekli çalışır (systemd service)
```

**Önemli Notlar:**
- Camera Snapshot her saat başı çalışır (09:00, 10:00, ..., 21:00)
- Batch Processor ve PTZ Analysis Service her saatin 30. dakikasında çalışır (09:30, 10:30, ..., 21:30)
- Her iki analiz servisi de aynı S3 snapshot'larını kullanır ama farklı analiz yöntemleri uygular
- Batch Processor: API tabanlı analiz (doluluk ve reyon sıralaması için)
- PTZ Analysis Service: YOLO + LLM tabanlı analiz (çürük tespiti için)

---

## 🚀 Servisleri Başlatma

### 1. Manav Analiz API (Systemd Service)

Manav API sürekli çalışması gerektiği için systemd service olarak yapılandırılır:

#### 1.1. Systemd Service Dosyası Oluşturma

```bash
sudo nano /etc/systemd/system/manav-api.service
```

İçerik:

```ini
[Unit]
Description=Manav Analiz API Service
After=network.target

[Service]
Type=simple
User=pam_aiuser
WorkingDirectory=/data/carrefoursa-kamera/CarrefourSa_Grocery/doluluk&reyonsıralaması/manav_analiz
Environment="PATH=/data/carrefoursa-kamera/CarrefourSa_Grocery/venv/bin"
ExecStart=/data/carrefoursa-kamera/CarrefourSa_Grocery/venv/bin/uvicorn main:app --host 0.0.0.0 --port 8000
Restart=always
RestartSec=10
StandardOutput=append:/data/carrefoursa-kamera/CarrefourSa_Grocery/logs/manav-api.log
StandardError=append:/data/carrefoursa-kamera/CarrefourSa_Grocery/logs/manav-api-error.log

[Install]
WantedBy=multi-user.target
```

**Not**: `User=pam_aiuser` kısmını kendi kullanıcı adınızla değiştirin.

#### 1.2. Servisi Başlatma

```bash
# Systemd'yi yeniden yükle
sudo systemctl daemon-reload

# Servisi etkinleştir (otomatik başlatma için)
sudo systemctl enable manav-api.service

# Servisi başlat
sudo systemctl start manav-api.service

# Durumunu kontrol et
sudo systemctl status manav-api.service
```

### 2. Wrapper Script'leri Oluşturma

Wrapper script'ler, Python script'lerini cron job'lardan çalıştırmak için kullanılan bash script'leridir. Bu script'ler:
- Virtual environment'ı otomatik aktif eder
- Doğru dizine geçer
- Python script'lerini çalıştırır
- Hata kontrolü yapar
- Log dosyalarına çıktı yazar

**ÖNEMLİ NOT**: Wrapper script'leri oluştururken **virtual environment'ın aktif olmasına gerek yoktur**. Wrapper script'ler bash script'leridir ve Python ortamından bağımsızdır. Virtual environment, script çalıştırıldığında script içinde otomatik olarak aktif edilir.

#### 2.1. Camera Snapshot Wrapper Script

**Adım 1: Script dosyasını oluşturun**
```bash
cd /data/carrefoursa-kamera/CarrefourSa_Grocery
nano run_camera_snapshot.sh
```

**Adım 2: Aşağıdaki içeriği yapıştırın**
```bash
#!/bin/bash
# Camera Snapshot Wrapper Script
# Bu script, camera_snapshot_system.py'yi çalıştırmak için kullanılır

# Proje dizinine geç
cd /data/carrefoursa-kamera/CarrefourSa_Grocery

# Virtual environment'ı aktif et
source venv/bin/activate

# Log dizinini oluştur (yoksa)
mkdir -p logs

# Camera Snapshot System'i çalıştır
python multi_camera_system/camera_snapshot_system.py
```

**Adım 3: Dosyayı kaydedin ve çıkın**
- `nano` kullanıyorsanız: `Ctrl+X`, sonra `Y`, sonra `Enter`
- `vi` kullanıyorsanız: `Esc`, sonra `:wq`, sonra `Enter`

**Adım 4: Script'e çalıştırma izni verin**
```bash
chmod +x run_camera_snapshot.sh
```

**Adım 5: Script'i test edin (opsiyonel)**
```bash
./run_camera_snapshot.sh
```

#### 2.2. Batch Processor Wrapper Script

**Adım 1: Script dosyasını oluşturun**
```bash
cd /data/carrefoursa-kamera/CarrefourSa_Grocery
nano run_batch_processor.sh
```

**Adım 2: Aşağıdaki içeriği yapıştırın**
```bash
#!/bin/bash
# Batch Processor Wrapper Script
# Bu script, batch_processor.py'yi çalıştırmak için kullanılır

# Proje dizinine geç
cd /data/carrefoursa-kamera/CarrefourSa_Grocery/doluluk\&reyonsıralaması/manav_analiz

# Virtual environment'ı aktif et
source ../../venv/bin/activate

# Batch processor'ı çalıştır (mod 2: Tam analiz)
# echo "2" komutu, batch_processor.py'nin interaktif mod seçimine "2" cevabını verir
echo "2" | python batch_processor.py
```

**Adım 3: Dosyayı kaydedin ve çıkın**
- `nano` kullanıyorsanız: `Ctrl+X`, sonra `Y`, sonra `Enter`

**Adım 4: Script'e çalıştırma izni verin**
```bash
chmod +x run_batch_processor.sh
```

**Adım 5: Script'i test edin (opsiyonel)**
```bash
./run_batch_processor.sh
```

#### 2.3. PTZ Analysis Service Wrapper Script

Bu script, 3 ayrı Python script'ini sırayla çalıştırır:
1. `ptz_face_blur.py` (opsiyonel - şu an kapalı)
2. `ptz_yolo_llm_analysis.py` (YOLO detection ve LLM analizi)
3. `ptz_db_writer.py` (Veritabanına yazma)

**Adım 1: Script dosyasını oluşturun**
```bash
cd /data/carrefoursa-kamera/CarrefourSa_Grocery
nano run_ptz_analysis.sh
```

**Adım 2: Aşağıdaki içeriği yapıştırın**
```bash
#!/bin/bash
# PTZ Analysis Service Wrapper Script
# Bu script, PTZ analiz servislerini sırayla çalıştırır

# Proje dizinine geç
cd /data/carrefoursa-kamera/CarrefourSa_Grocery

# Virtual environment'ı aktif et
source venv/bin/activate

# Log dizinini oluştur (yoksa)
mkdir -p logs

# ============================================
# AŞAMA 1: Yüz Blur'lanması (OPSİYONEL)
# ============================================
# Şu an kapalı, gerekirse yorum satırını kaldırın
# echo "[$(date '+%Y-%m-%d %H:%M:%S')] PTZ Face Blur başlatılıyor..."
# python ptz_face_blur.py >> logs/cron-ptz-face-blur.log 2>&1
# FACE_BLUR_EXIT_CODE=$?
# if [ $FACE_BLUR_EXIT_CODE -ne 0 ]; then
#     echo "[$(date '+%Y-%m-%d %H:%M:%S')] PTZ Face Blur hatası: $FACE_BLUR_EXIT_CODE"
#     exit $FACE_BLUR_EXIT_CODE
# fi

# ============================================
# AŞAMA 2: YOLO Detection ve LLM Analizi
# ============================================
echo "[$(date '+%Y-%m-%d %H:%M:%S')] PTZ YOLO + LLM Analysis başlatılıyor..."
python ptz_yolo_llm_analysis.py >> logs/cron-ptz-yolo-llm.log 2>&1
YOLO_EXIT_CODE=$?

# YOLO analizi başarılı mı kontrol et
if [ $YOLO_EXIT_CODE -eq 0 ]; then
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] PTZ YOLO + LLM Analysis tamamlandı"
    
    # ============================================
    # AŞAMA 3: Veritabanına Yazma
    # ============================================
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] PTZ Database Writer başlatılıyor..."
    python ptz_db_writer.py >> logs/cron-ptz-db-writer.log 2>&1
    DB_EXIT_CODE=$?
    
    # Veritabanı yazma başarılı mı kontrol et
    if [ $DB_EXIT_CODE -eq 0 ]; then
        echo "[$(date '+%Y-%m-%d %H:%M:%S')] PTZ Database Writer tamamlandı"
        echo "[$(date '+%Y-%m-%d %H:%M:%S')] Tüm PTZ analiz işlemleri başarıyla tamamlandı"
        exit 0
    else
        echo "[$(date '+%Y-%m-%d %H:%M:%S')] PTZ Database Writer hatası: $DB_EXIT_CODE"
        exit $DB_EXIT_CODE
    fi
else
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] PTZ YOLO + LLM Analysis hatası: $YOLO_EXIT_CODE"
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] Veritabanı yazma işlemi atlandı (YOLO analizi başarısız)"
    exit $YOLO_EXIT_CODE
fi
```

**Adım 3: Dosyayı kaydedin ve çıkın**
- `nano` kullanıyorsanız: `Ctrl+X`, sonra `Y`, sonra `Enter`

**Adım 4: Script'e çalıştırma izni verin**
```bash
chmod +x run_ptz_analysis.sh
```

**Adım 5: Script'i test edin (opsiyonel)**
```bash
./run_ptz_analysis.sh

# Log dosyalarını kontrol edin
tail -f logs/cron-ptz-yolo-llm.log
tail -f logs/cron-ptz-db-writer.log
```

#### 2.4. Alternatif: Tek Komutla Oluşturma

Eğer yukarıdaki adımları tek tek yapmak istemiyorsanız, aşağıdaki komutları kullanabilirsiniz:

```bash
# Camera Snapshot wrapper script
cat > /data/carrefoursa-kamera/CarrefourSa_Grocery/run_camera_snapshot.sh << 'EOF'
#!/bin/bash
cd /data/carrefoursa-kamera/CarrefourSa_Grocery
source venv/bin/activate
mkdir -p logs
python multi_camera_system/camera_snapshot_system.py
EOF

chmod +x /data/carrefoursa-kamera/CarrefourSa_Grocery/run_camera_snapshot.sh

# Batch Processor wrapper script
cat > /data/carrefoursa-kamera/CarrefourSa_Grocery/run_batch_processor.sh << 'EOF'
#!/bin/bash
cd /data/carrefoursa-kamera/CarrefourSa_Grocery/doluluk\&reyonsıralaması/manav_analiz
source ../../venv/bin/activate
echo "2" | python batch_processor.py
EOF

chmod +x /data/carrefoursa-kamera/CarrefourSa_Grocery/run_batch_processor.sh

# PTZ Analysis Service wrapper script
cat > /data/carrefoursa-kamera/CarrefourSa_Grocery/run_ptz_analysis.sh << 'EOF'
#!/bin/bash
cd /data/carrefoursa-kamera/CarrefourSa_Grocery
source venv/bin/activate
mkdir -p logs

echo "[$(date '+%Y-%m-%d %H:%M:%S')] PTZ YOLO + LLM Analysis başlatılıyor..."
python ptz_yolo_llm_analysis.py >> logs/cron-ptz-yolo-llm.log 2>&1
YOLO_EXIT_CODE=$?

if [ $YOLO_EXIT_CODE -eq 0 ]; then
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] PTZ YOLO + LLM Analysis tamamlandı"
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] PTZ Database Writer başlatılıyor..."
    python ptz_db_writer.py >> logs/cron-ptz-db-writer.log 2>&1
    DB_EXIT_CODE=$?
    
    if [ $DB_EXIT_CODE -eq 0 ]; then
        echo "[$(date '+%Y-%m-%d %H:%M:%S')] PTZ Database Writer tamamlandı"
        exit 0
    else
        echo "[$(date '+%Y-%m-%d %H:%M:%S')] PTZ Database Writer hatası: $DB_EXIT_CODE"
        exit $DB_EXIT_CODE
    fi
else
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] PTZ YOLO + LLM Analysis hatası: $YOLO_EXIT_CODE"
    exit $YOLO_EXIT_CODE
fi
EOF

chmod +x /data/carrefoursa-kamera/CarrefourSa_Grocery/run_ptz_analysis.sh
```

#### 2.5. Script İçeriği Açıklamaları

**`#!/bin/bash`**: Script'in bash ile çalıştırılacağını belirtir

**`cd /path/to/directory`**: Script'in çalışacağı dizini belirtir

**`source venv/bin/activate`**: Virtual environment'ı aktif eder

**`>> logs/file.log 2>&1`**: 
- `>>`: Çıktıyı dosyaya ekler (üzerine yazmaz)
- `2>&1`: Hata mesajlarını da aynı dosyaya yazar

**`EXIT_CODE=$?`**: Son çalıştırılan komutun çıkış kodunu saklar (0 = başarılı, 0 dışı = hata)

**`if [ $EXIT_CODE -eq 0 ]`**: Çıkış kodu 0 ise (başarılı) işlem yapar

**`exit $EXIT_CODE`**: Script'i belirtilen çıkış kodu ile sonlandırır (cron job hata durumunu anlayabilir)

#### 2.6. Script'leri Kontrol Etme

```bash
# Script dosyalarının varlığını kontrol edin
ls -lh /data/carrefoursa-kamera/CarrefourSa_Grocery/run_*.sh

# Script'lerin çalıştırılabilir olduğunu kontrol edin (x izni olmalı)
ls -l /data/carrefoursa-kamera/CarrefourSa_Grocery/run_*.sh

# Script içeriklerini görüntüleyin
cat /data/carrefoursa-kamera/CarrefourSa_Grocery/run_camera_snapshot.sh
cat /data/carrefoursa-kamera/CarrefourSa_Grocery/run_batch_processor.sh
cat /data/carrefoursa-kamera/CarrefourSa_Grocery/run_ptz_analysis.sh
```

### 3. Cron Job Yapılandırması

Camera Snapshot, Batch Processor ve PTZ Analysis Service, belirli saatlerde çalışması gerektiği için cron job olarak yapılandırılır:

```bash
# Crontab'ı düzenle
crontab -e

# Aşağıdaki satırları ekle:

# Camera Snapshot: Her gün 09:00-21:00 arası her saat başı çalışır
0 9-21 * * * /data/carrefoursa-kamera/CarrefourSa_Grocery/run_camera_snapshot.sh >> /data/carrefoursa-kamera/CarrefourSa_Grocery/logs/cron-snapshot.log 2>&1

# Batch Processor: Her gün 09:30-21:30 arası çalışır (camera-snapshot'tan 30 dakika sonra)
30 9-21 * * * /data/carrefoursa-kamera/CarrefourSa_Grocery/run_batch_processor.sh >> /data/carrefoursa-kamera/CarrefourSa_Grocery/logs/cron-batch.log 2>&1

# PTZ Analysis Service: Her gün 09:30-21:30 arası çalışır (camera-snapshot'tan 30 dakika sonra)
30 9-21 * * * /data/carrefoursa-kamera/CarrefourSa_Grocery/run_ptz_analysis.sh >> /data/carrefoursa-kamera/CarrefourSa_Grocery/logs/cron-ptz-analysis.log 2>&1
```

**Cron Job Formatı Açıklaması:**
```
* * * * * komut
│ │ │ │ │
│ │ │ │ └─── Haftanın günü (0-7, 0 ve 7 = Pazar)
│ │ │ └───── Ay (1-12)
│ │ └─────── Ayın günü (1-31)
│ └───────── Saat (0-23)
└─────────── Dakika (0-59)
```

**Örnekler:**
- `0 9-21 * * *` → Her gün 09:00-21:00 arası her saat başı (09:00, 10:00, ..., 21:00)
- `30 9-21 * * *` → Her gün 09:30-21:30 arası her saatin 30. dakikasında (09:30, 10:30, ..., 21:30)

### 4. Cron Job'ları Kontrol Etme

```bash
# Aktif cron job'ları listele
crontab -l

# Cron loglarını kontrol et (sistem logları)
sudo tail -f /var/log/syslog | grep CRON

# Uygulama loglarını kontrol et
tail -f /data/carrefoursa-kamera/CarrefourSa_Grocery/logs/cron-snapshot.log
tail -f /data/carrefoursa-kamera/CarrefourSa_Grocery/logs/cron-batch.log
tail -f /data/carrefoursa-kamera/CarrefourSa_Grocery/logs/cron-ptz-analysis.log

# Tüm logları birlikte izle
tail -f /data/carrefoursa-kamera/CarrefourSa_Grocery/logs/cron-*.log
```

---

## 📊 İzleme ve Loglar

### Log Dosyaları

```bash
# Log dizinini oluştur
mkdir -p /data/carrefoursa-kamera/CarrefourSa_Grocery/logs

# Log dosyalarını izle
# Manav API (systemd service)
tail -f /data/carrefoursa-kamera/CarrefourSa_Grocery/logs/manav-api.log
tail -f /data/carrefoursa-kamera/CarrefourSa_Grocery/logs/manav-api-error.log

# Camera Snapshot (cron job)
tail -f /data/carrefoursa-kamera/CarrefourSa_Grocery/logs/cron-snapshot.log

# Batch Processor (cron job)
tail -f /data/carrefoursa-kamera/CarrefourSa_Grocery/logs/cron-batch.log

# PTZ Analysis Service (cron job)
tail -f /data/carrefoursa-kamera/CarrefourSa_Grocery/logs/cron-ptz-analysis.log

# PTZ Analysis Service alt loglar (ayrı ayrı)
tail -f /data/carrefoursa-kamera/CarrefourSa_Grocery/logs/cron-ptz-face-blur.log
tail -f /data/carrefoursa-kamera/CarrefourSa_Grocery/logs/cron-ptz-yolo-llm.log
tail -f /data/carrefoursa-kamera/CarrefourSa_Grocery/logs/cron-ptz-db-writer.log

# Tüm logları izle
tail -f /data/carrefoursa-kamera/CarrefourSa_Grocery/logs/*.log
```

### Servis Durumlarını Kontrol Etme

```bash
# Manav API servis durumunu kontrol et (systemd)
sudo systemctl status manav-api.service

# Manav API'yi yeniden başlat
sudo systemctl restart manav-api.service

# Manav API'yi durdur
sudo systemctl stop manav-api.service

# Aktif cron job'ları kontrol et
crontab -l

# Son çalışan cron job'ları kontrol et
sudo grep CRON /var/log/syslog | tail -20
```

### API Health Check

```bash
# API'nin çalışıp çalışmadığını kontrol et
curl http://localhost:8000/health

# API bilgilerini görüntüle
curl http://localhost:8000/
```

### S3 Object Storage Kontrolü

```bash
# S3 bağlantısını test et
source venv/bin/activate
python3 test_s3_upload.py

# S3'teki fotoğrafları kontrol et (Python ile)
python3 -c "
import boto3
import os
from dotenv import load_dotenv
load_dotenv()

s3 = boto3.client('s3',
    endpoint_url=os.getenv('S3_ENDPOINT_URL'),
    aws_access_key_id=os.getenv('S3_ACCESS_KEY_ID'),
    aws_secret_access_key=os.getenv('S3_SECRET_ACCESS_KEY'),
    verify=False
)

# snapshots prefix'i altındaki object'leri listele
response = s3.list_objects_v2(Bucket=os.getenv('S3_BUCKET_NAME'), Prefix='snapshots/', MaxKeys=20)
if 'Contents' in response:
    print(f'Toplam {len(response[\"Contents\"])} object bulundu (ilk 20):')
    for obj in response['Contents']:
        print(f'  - {obj[\"Key\"]} ({obj[\"Size\"]} bytes)')
else:
    print('snapshots/ prefix\'i altında object bulunamadı')
"
```

---

## 🔧 Sorun Giderme

### 1. Python Virtual Environment Sorunları

```bash
# Virtual environment'ı yeniden oluştur
deactivate  # Eğer aktifse
rm -rf venv
python3 -m venv venv
source venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
```

### 2. Bağımlılık Sorunları

```bash
# Tüm paketleri güncelle
pip install --upgrade -r requirements.txt

# Özel paket sorunları için
pip install --force-reinstall <package-name>
```

### 3. İzin Sorunları

```bash
# Dosya sahipliklerini kontrol et
ls -la /data/carrefoursa-kamera/CarrefourSa_Grocery

# Gerekirse sahiplik değiştir
sudo chown -R $USER:$USER /data/carrefoursa-kamera
```

### 4. Port Kullanımı

```bash
# Port 8000'in kullanımda olup olmadığını kontrol et
sudo netstat -tulpn | grep 8000
# veya
sudo ss -tulpn | grep 8000

# Eğer kullanılıyorsa, process'i bul ve durdur
sudo lsof -i :8000
```

### 5. PostgreSQL Bağlantı Sorunları

```bash
# PostgreSQL bağlantısını test et
psql -h 45.84.18.76 -U grocerryadmin -d grocerryadmin

# Python'dan test
source venv/bin/activate
python3 -c "import psycopg2; conn = psycopg2.connect('postgresql://grocerryadmin:a08Iyr95vLHTYY@45.84.18.76:5432/grocerryadmin?sslmode=prefer'); print('Bağlantı başarılı!')"
```

**Not**: PostgreSQL sunucusu SSL desteklemiyorsa, kod otomatik olarak `sslmode=prefer` kullanır (SSL varsa kullanır, yoksa SSL olmadan bağlanır).

### 6. S3 Bağlantı Sorunları

```bash
# S3 bağlantısını test et
source venv/bin/activate
python3 test_s3_upload.py
```

**Olası Sorunlar ve Çözümler:**

1. **S3 credentials tanımlı değil**
   - Çözüm: `.env` dosyasında `S3_ACCESS_KEY_ID` ve `S3_SECRET_ACCESS_KEY` değerlerini kontrol edin

2. **S3 client oluşturulamıyor**
   - Çözüm: Endpoint URL'ini ve credentials'ı kontrol edin

3. **Bucket bulunamıyor**
   - Çözüm: Bucket adını kontrol edin (`Grocery`)

4. **Yükleme başarısız**
   - Çözüm: Log dosyalarını kontrol edin (`logs/cron-snapshot.log`)

### 7. Sistem Saati Sorunları

**ÖNEMLİ**: Sistem saati yanlışsa, fotoğrafların tarih/saat bilgileri ve klasör yapısı yanlış olur.

#### 7.1. Sistem Saatini Kontrol Etme

```bash
# Mevcut sistem saatini kontrol et
date

# Timezone'u kontrol et
timedatectl

# UTC saatini kontrol et
date -u
```

#### 7.2. Sistem Saatini Düzeltme (Önerilen)

```bash
# Timezone'u Türkiye saati (Europe/Istanbul) olarak ayarla
sudo timedatectl set-timezone Europe/Istanbul

# NTP ile senkronize et (otomatik saat düzeltme)
sudo timedatectl set-ntp true

# Saati kontrol et
date
timedatectl
```

#### 7.3. Kod İçinde Saat Düzeltmesi

**Not**: Kod zaten Türkiye saatini (UTC+3) kullanacak şekilde yapılandırılmıştır. Sistem saati yanlış olsa bile, kod UTC'den Türkiye saatine çevirir. Ancak sistem saatini düzeltmek daha iyidir çünkü:
- Cron job'lar doğru saatte çalışır
- Log dosyaları doğru tarih/saat ile oluşturulur
- Tüm sistem tutarlı olur

Kod içinde saat düzeltmesi:
- `camera_snapshot_system.py` → `get_turkey_time()` fonksiyonu kullanılıyor
- Fotoğraf klasör yapısı ve S3 key'leri Türkiye saatine göre oluşturuluyor

### 8. S3'te Fotoğraf Görünmüyor

**Olası Nedenler:**

1. **S3 credentials yanlış veya tanımlı değil**
   - Çözüm: `.env` dosyasını kontrol edin, `test_s3_upload.py` script'ini çalıştırın

2. **S3'e yükleme başarısız oluyor**
   - Çözüm: `logs/cron-snapshot.log` dosyasını kontrol edin, `[HATA]` veya `[UYARI]` mesajlarını arayın

3. **Bucket veya prefix yanlış**
   - Çözüm: Bucket adı `Grocery`, prefix `snapshots/` olmalı

4. **Fotoğraflar henüz çekilmemiş**
   - Çözüm: Camera Snapshot System'in çalıştığından emin olun

**Kontrol Komutları:**

```bash
# S3 test script'ini çalıştır
python3 test_s3_upload.py

# Camera Snapshot log'larını kontrol et
tail -100 logs/cron-snapshot.log | grep -i "s3\|upload\|hata"

# S3'teki object'leri listele
python3 -c "
import boto3
import os
from dotenv import load_dotenv
load_dotenv()

s3 = boto3.client('s3',
    endpoint_url=os.getenv('S3_ENDPOINT_URL'),
    aws_access_key_id=os.getenv('S3_ACCESS_KEY_ID'),
    aws_secret_access_key=os.getenv('S3_SECRET_ACCESS_KEY'),
    verify=False
)

response = s3.list_objects_v2(Bucket=os.getenv('S3_BUCKET_NAME'), Prefix='snapshots/', MaxKeys=50)
if 'Contents' in response:
    print(f'Toplam {len(response[\"Contents\"])} object bulundu:')
    for obj in response['Contents']:
        print(f'  {obj[\"Key\"]}')
else:
    print('snapshots/ prefix\'i altında object bulunamadı')
"
```

---

## 📝 Hızlı Başlangıç Özeti

```bash
# 1. Projeyi kopyala
cd /data
sudo mkdir -p carrefoursa-kamera/CarrefourSa_Grocery
sudo chown $USER:$USER carrefoursa-kamera
cd carrefoursa-kamera/CarrefourSa_Grocery
# Projeyi buraya kopyala

# 2. Virtual environment oluştur
python3 -m venv venv
source venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt

# 3. .env dosyası oluştur
nano .env
# Yukarıdaki .env içeriğini yapıştır

# 4. Dizinleri oluştur
mkdir -p snapshots crops logs

# 5. Sistem saatini ayarla
sudo timedatectl set-timezone Europe/Istanbul
sudo timedatectl set-ntp true

# 6. Manav API systemd service dosyasını oluştur
sudo nano /etc/systemd/system/manav-api.service
# Yukarıdaki manav-api service içeriğini yapıştır

# 7. Manav API servisini başlat
sudo systemctl daemon-reload
sudo systemctl enable manav-api.service
sudo systemctl start manav-api.service

# 8. Wrapper script'leri oluştur
# run_camera_snapshot.sh, run_batch_processor.sh ve run_ptz_analysis.sh script'lerini oluştur (yukarıdaki örneklere göre)

# 9. Cron job'ları yapılandır
crontab -e
# Aşağıdaki satırları ekle:
# 0 9-21 * * * /data/carrefoursa-kamera/CarrefourSa_Grocery/run_camera_snapshot.sh >> /data/carrefoursa-kamera/CarrefourSa_Grocery/logs/cron-snapshot.log 2>&1
# 30 9-21 * * * /data/carrefoursa-kamera/CarrefourSa_Grocery/run_batch_processor.sh >> /data/carrefoursa-kamera/CarrefourSa_Grocery/logs/cron-batch.log 2>&1
# 30 9-21 * * * /data/carrefoursa-kamera/CarrefourSa_Grocery/run_ptz_analysis.sh >> /data/carrefoursa-kamera/CarrefourSa_Grocery/logs/cron-ptz-analysis.log 2>&1

# 10. Durumları kontrol et
sudo systemctl status manav-api
crontab -l

# 11. S3 bağlantısını test et
python3 test_s3_upload.py
```

---

## ⚠️ Önemli Notlar

### 1. Servis Bağımlılıkları

- **Manav API** → Batch Processor tarafından kullanılıyor (7/24 çalışmalı)
- **Camera Snapshot** → Batch Processor ve PTZ Analysis Service tarafından kullanılıyor (S3'e görüntü yükler)
- **Batch Processor** → Manav API'ye bağımlı (API çalışmalı)
- **PTZ Analysis Service** → Bağımsız çalışır (sadece S3 ve PostgreSQL'e bağlanır)

### 2. S3 Object Storage

- **Bucket**: `Grocery`
- **Prefix**: `snapshots/` (fotoğraflar için)
- **Format**: `snapshots/camera_XXX/YYYY-MM-DD/HH/filename.jpg`
- Fotoğraflar S3'e yüklendikten sonra lokal dosyalar silinir

### 3. PostgreSQL Veritabanı

- **Host**: `45.84.18.76`
- **Port**: `5432`
- **Database**: `grocerryadmin`
- **User**: `grocerryadmin`
- **SSL Mode**: `prefer` (SSL varsa kullanır, yoksa SSL olmadan bağlanır)

### 4. Sistem Saati

- Kod Türkiye saatini (UTC+3) kullanır
- Sistem saatini düzeltmek önerilir (cron job'lar için)
- Sistem saati yanlış olsa bile kod doğru saati kullanır

### 5. Wrapper Script'ler

- 3 adet wrapper script gerekli:
  1. `run_camera_snapshot.sh` - Camera Snapshot System için
  2. `run_batch_processor.sh` - Batch Processor için
  3. `run_ptz_analysis.sh` - PTZ Analysis Service için (3 script'i sırayla çalıştırır)

---

## 🔐 Güvenlik Notları

1. **.env dosyası**: Hassas bilgiler içerir, asla Git'e commit etmeyin
2. **Firewall**: Gerekli portları açın (8000, vb.)
3. **SSL/TLS**: Production'da HTTPS kullanın (nginx reverse proxy ile)
4. **Kullanıcı İzinleri**: Servisleri özel bir kullanıcı ile çalıştırın
5. **Log Rotation**: Log dosyalarının büyümesini önlemek için logrotate kullanın

---

## 📞 Destek

Sorun yaşarsanız:
1. Log dosyalarını kontrol edin
2. Servis durumlarını kontrol edin
3. Network bağlantılarını test edin
4. Environment variables'ları doğrulayın
5. `test_s3_upload.py` script'ini çalıştırarak S3 bağlantısını test edin
