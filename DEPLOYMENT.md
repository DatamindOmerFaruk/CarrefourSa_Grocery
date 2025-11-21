# Linux Sunucu Deployment Rehberi

Bu rehber, tüm projeyi Linux sunucuda çalıştırmak için gerekli adımları içerir.

## 📋 İçindekiler

1. [Sistem Gereksinimleri](#sistem-gereksinimleri)
2. [Kurulum Adımları](#kurulum-adımları)
3. [Konfigürasyon](#konfigürasyon)
4. [Servisler Hakkında](#servisler-hakkında)
5. [Servisleri Başlatma](#servisleri-başlatma)
6. [Cronjob Kurulum](#cronjob-kurulum)
7. [İzleme ve Loglar](#izleme-ve-loglar)
8. [Sorun Giderme](#sorun-giderme)
9. [Sistem Mimarisi](#sistem-mimarisi)

---

## 🖥️ Sistem Gereksinimleri

- **OS**: Ubuntu 20.04+ / Debian 11+ / CentOS 8+ / RHEL 8+
- **Python**: 3.10 veya üzeri
- **RAM**: 8 GB (16 GB önerilir)
- **Disk**: 50 GB boş alan

### Gerekli Sistem Paketleri

```bash
sudo apt-get update
sudo apt-get install -y python3 python3-pip python3-venv git build-essential libpq-dev postgresql-client curl wget
```

---

## 📦 Kurulum Adımları

### 1. Projeyi Sunucuya Kopyalama

```bash
sudo mkdir -p /data/carrefoursa-kamera/CarrefourSa_Grocery
sudo chown $USER:$USER /data/carrefoursa-kamera
cd /data/carrefoursa-kamera/CarrefourSa_Grocery
# Projeyi buraya kopyala (Git veya SCP ile)
```

### 2. Python Virtual Environment ve Bağımlılıklar

```bash
python3 -m venv venv
source venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
```

### 3. Dizinleri Oluşturma

```bash
mkdir -p snapshots crops logs
```

### 4. Sistem Saatini Ayarlama

```bash
sudo timedatectl set-timezone Europe/Istanbul
sudo timedatectl set-ntp true
```

---

## ⚙️ Konfigürasyon

### .env Dosyası Oluşturma

```bash
nano .env
```

`.env` dosyası içeriği:

```bash
# S3 Object Storage
S3_ENDPOINT_URL=https://161cohesity.carrefoursa.com:3000
S3_ACCESS_KEY_ID=sWxdTl3ERx7myBE1qpW06_haVvuhATcdsmBbqaWkXYU
S3_SECRET_ACCESS_KEY=Ti9Fonk3wYyG5PMx5LaGUmlcVyCuqsE5BLVV5vv8PU0
S3_BUCKET_NAME=Grocery

# PostgreSQL
PG_HOST=45.84.18.76
PG_PORT=5432
PG_USER=grocerryadmin
PG_PASSWORD=a08Iyr95vLHTYY
PG_DATABASE=postgres
PG_DSN=postgresql://grocerryadmin:a08Iyr95vLHTYY@45.84.18.76:5432/postgres

# Azure OpenAI
AZURE_OPENAI_ENDPOINT=https://your-endpoint.openai.azure.com/
AZURE_OPENAI_API_KEY=your-api-key
AZURE_OPENAI_DEPLOYMENT=gpt-4.1
AZURE_API_VERSION=2024-06-01

# API Ayarları
API_BASE_URL=http://localhost:8000
BATCH_SIZE=10
RETRY_COUNT=3
REQUEST_DELAY=1.0

# Diğer
MIN_CONF_ROTTEN=0.85
TEST_MODE=false
```

---

## 🚀 Servisler Hakkında

Sistemde 4 ana servis bulunmaktadır:

1. **Camera Snapshot System** - PTZ kameralardan görüntü alır, YOLO ile insan tespiti yapar, S3'e yükler
   - Çalışma: Cron job ile saatlik (09:00-21:00, her saat başı)

2. **Manav Analiz API** - FastAPI REST API servisi (Port: 8000)
   - Çalışma: Systemd service olarak 7/24 sürekli

3. **Batch Processor** - S3'ten görüntüleri alır, API'ye gönderir, PostgreSQL'e kaydeder
   - Çalışma: Cron job ile saatlik (09:35-21:35, her saatin 35. dakikasında)

4. **PTZ Analysis Service** - YOLO detection, LLM analizi, çürük tespiti
   - Çalışma: Cron job ile saatlik (09:20-21:20, her saatin 20. dakikasında)
   - Script'ler: `ptz_face_blur.py` → `ptz_yolo_llm_analysis.py` → `ptz_db_writer.py`

---

## 🚀 Servisleri Başlatma

### 1. Manav Analiz API (Systemd Service)

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

Servisi başlatma:

```bash
sudo systemctl daemon-reload
sudo systemctl enable manav-api.service
sudo systemctl start manav-api.service
sudo systemctl status manav-api.service
```

### 2. Wrapper Script'leri Oluşturma

```bash
chmod +x create_wrapper_scripts.sh
./create_wrapper_scripts.sh
```

Bu script otomatik olarak şu dosyaları oluşturur:
- `run_camera_snapshot.sh`
- `run_batch_processor.sh`
- `run_ptz_analysis.sh`

---

## ⏰ Cronjob Kurulum

### Hızlı Kurulum

```bash
# 1. Wrapper script'leri oluştur (yukarıda yapıldı)

# 2. Cronjob'ları kur
chmod +x setup_cronjobs.sh
./setup_cronjobs.sh

# 3. Kontrol et
chmod +x check_cronjobs.sh
./check_cronjobs.sh
```

### Cronjob Zamanlaması

| Script | Zaman | Format |
|--------|-------|--------|
| Camera Snapshot | Her saat başı (9:00-21:00) | `0 9-21 * * *` |
| Batch Processor | Her saat 35'de (9:35-21:35) | `35 9-21 * * *` |
| PTZ Analysis | Her saat 20'de (9:20-21:20) | `20 9-21 * * *` |

### Manuel Kurulum (Alternatif)

```bash
crontab -e
```

Aşağıdaki satırları ekle:

```
0 9-21 * * * /data/carrefoursa-kamera/CarrefourSa_Grocery/run_camera_snapshot.sh >> /data/carrefoursa-kamera/CarrefourSa_Grocery/logs/cron-snapshot.log 2>&1
35 9-21 * * * /data/carrefoursa-kamera/CarrefourSa_Grocery/run_batch_processor.sh >> /data/carrefoursa-kamera/CarrefourSa_Grocery/logs/cron-batch.log 2>&1
20 9-21 * * * /data/carrefoursa-kamera/CarrefourSa_Grocery/run_ptz_analysis.sh >> /data/carrefoursa-kamera/CarrefourSa_Grocery/logs/cron-ptz-analysis.log 2>&1
```

---

## 📊 İzleme ve Loglar

### Log Dosyaları

```bash
# Manav API
tail -f logs/manav-api.log
tail -f logs/manav-api-error.log

# Cron job'lar
tail -f logs/cron-snapshot.log
tail -f logs/cron-batch.log
tail -f logs/cron-ptz-analysis.log
tail -f logs/cron-*.log  # Tüm logları izle
```

### Servis Durumları

```bash
# Manav API
sudo systemctl status manav-api.service
sudo systemctl restart manav-api.service

# Cron job'lar
crontab -l
sudo grep CRON /var/log/syslog | tail -20
```

### API Health Check

```bash
curl http://localhost:8000/health
```

---

## 🔧 Sorun Giderme

### Virtual Environment Sorunları

```bash
rm -rf venv
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### Cronjob Sorunları

```bash
# Teşhis script'ini çalıştır
./check_cronjobs.sh

# Cron servisini kontrol et
sudo systemctl status cron
sudo systemctl start cron

# Script'leri manuel test et
./run_camera_snapshot.sh
./run_batch_processor.sh
./run_ptz_analysis.sh
```

### Yaygın Sorunlar

**"command not found" hatası:**
- Script'lerde PATH tanımlı değil, `create_wrapper_scripts.sh` kullanın

**"Permission denied" hatası:**
```bash
chmod +x run_*.sh
```

**Port 8000 kullanımda:**
```bash
sudo lsof -i :8000
sudo systemctl stop manav-api.service
```

**S3 bağlantı sorunları:**
- `.env` dosyasındaki S3 credentials'ı kontrol edin
- `logs/cron-snapshot.log` dosyasını kontrol edin

**PostgreSQL bağlantı sorunları:**
```bash
psql -h 45.84.18.76 -U grocerryadmin -d postgres
```

---

## 🏗️ Sistem Mimarisi

### Veri Akışı

```
1. Kamera Sistemi → PTZ Snapshot → S3 Object Storage
2. Batch Processor → S3'ten görselleri listele → API çağrıları
3. FastAPI Service → Görüntü iyileştirme → Azure OpenAI GPT-4.1 Vision
4. Azure OpenAI → JSON Response → FastAPI → Batch Processor
5. Batch Processor → PostgreSQL'e kaydet
```

### Sistem Bileşenleri

- **Görüntü Kaynağı**: PTZ kameralardan snapshot
- **S3 Object Storage**: Görüntü deposu (Bucket: `Grocery`, Prefix: `snapshots/`)
- **Batch Processor**: S3'ten görüntüleri alır, API'ye gönderir
- **FastAPI Service**: Görüntü analizi endpoint'leri (Port: 8000)
- **Azure OpenAI**: GPT-4.1 Vision ile analiz
- **PostgreSQL**: Sonuç depolama

### Teknoloji Stack

- **Backend**: Python 3.x, FastAPI, Uvicorn
- **Cloud**: S3 Object Storage (Cohesity), Azure OpenAI
- **Database**: PostgreSQL, Psycopg2
- **Image Processing**: Pillow (PIL), YOLOv8/YOLOv12
- **Utilities**: Python-dotenv, Requests

---

## ⚠️ Önemli Notlar

1. **Servis Bağımlılıkları**:
   - Manav API → Batch Processor tarafından kullanılıyor (7/24 çalışmalı)
   - Camera Snapshot → Batch Processor ve PTZ Analysis Service tarafından kullanılıyor

2. **S3 Object Storage**:
   - Bucket: `Grocery`
   - Prefix: `snapshots/`
   - Format: `snapshots/camera_XXX/YYYY-MM-DD/HH/filename.jpg`

3. **PostgreSQL**:
   - Host: `45.84.18.76`
   - Port: `5432`
   - Database: `postgres`
   - SSL Mode: `prefer`

4. **Sistem Saati**:
   - Kod Türkiye saatini (UTC+3) kullanır
   - Sistem saatini düzeltmek önerilir (cron job'lar için)

5. **Güvenlik**:
   - `.env` dosyası hassas bilgiler içerir, Git'e commit etmeyin
   - Production'da HTTPS kullanın (nginx reverse proxy ile)

---

## 📞 Destek

Sorun yaşarsanız:
1. Log dosyalarını kontrol edin
2. Servis durumlarını kontrol edin
3. `./check_cronjobs.sh` script'ini çalıştırın
4. Environment variables'ları doğrulayın
