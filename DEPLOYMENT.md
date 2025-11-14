# Linux Sunucu Deployment Rehberi

Bu rehber, tüm projeyi Linux sunucuda çalıştırmak için gerekli adımları içerir.

## 📋 İçindekiler

1. [Sistem Gereksinimleri](#sistem-gereksinimleri)
2. [Kurulum Adımları](#kurulum-adımları)
3. [Konfigürasyon](#konfigürasyon)
4. [Servisleri Başlatma](#servisleri-başlatma)
5. [İzleme ve Loglar](#izleme-ve-loglar)
6. [Sorun Giderme](#sorun-giderme)

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
sudo mkdir -p /opt/carrefoursa-kamera
sudo chown $USER:$USER /opt/carrefoursa-kamera
cd /opt/carrefoursa-kamera

# Projeyi kopyala (GitHub'dan veya SCP ile)
# Örnek: Git kullanıyorsanız
git clone <repository-url> .

# Veya SCP ile Windows'tan kopyalama:
# scp -r "C:\Users\test\Desktop\Carrefoursa\reyon\Kamera Entegrasyon" user@server:/opt/carrefoursa-kamera
```

### 2. Python Virtual Environment Oluşturma

```bash
cd /opt/carrefoursa-kamera

# Virtual environment oluştur
python3 -m venv venv

# Virtual environment'ı aktif et
source venv/bin/activate

# Pip'i güncelle
pip install --upgrade pip setuptools wheel
```

### 3. Bağımlılıkları Yükleme

```bash
# Ana requirements dosyasını yükle
pip install -r requirements.txt

# Eğer requirements.txt yoksa, tüm bağımlılıkları manuel yükle:
pip install \
    requests>=2.32.0 \
    Pillow>=10.0.0 \
    PyYAML>=6.0.1 \
    numpy>=1.24.0 \
    ultralytics>=8.0.0 \
    torch>=2.0.0 \
    torchvision>=0.15.0 \
    fastapi==0.104.1 \
    uvicorn==0.24.0 \
    python-multipart==0.0.6 \
    python-dotenv==1.0.0 \
    boto3>=1.34.0 \
    psycopg2-binary>=2.9.0,<3.0.0 \
    azure-storage-blob==12.19.0 \
    facenet-pytorch \
    openai>=1.30.0
```

### 4. Model Dosyalarını Kontrol Etme

```bash
# YOLO model dosyalarının varlığını kontrol et
ls -lh best.pt yolov8s.pt

# Eğer yoksa, YOLO otomatik indirecek (ilk çalıştırmada)
```

---

## ⚙️ Konfigürasyon

### 1. Environment Variables (.env dosyası)

```bash
# .env dosyası oluştur
nano /opt/carrefoursa-kamera/.env
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

# Azure Storage (Batch Processor için - eğer kullanılıyorsa)
AZURE_STORAGE_CONNECTION_STRING=DefaultEndpointsProtocol=https;AccountName=...
AZURE_CONTAINER_NAME=snapshot
AZURE_SAS_TOKEN=...

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

### 2. Dosya İzinlerini Ayarlama

```bash
# Gerekli dizinleri oluştur
mkdir -p snapshots crops logs

# İzinleri ayarla
chmod 755 /opt/carrefoursa-kamera
chmod 644 /opt/carrefoursa-kamera/.env
```

### 3. Kamera Konfigürasyon Dosyalarını Kontrol Etme

```bash
# Kamera konfigürasyon dosyalarını kontrol et
ls -lh multi_camera_system/cameras.yaml
ls -lh multi_camera_system/cameras_reyon_genel.yaml

# İçeriklerini kontrol et ve gerekirse düzenle
nano multi_camera_system/cameras.yaml
```

---

## 🚀 Servisleri Başlatma

### 1. Systemd Service Dosyaları Oluşturma

#### Camera Snapshot System Service

```bash
sudo nano /etc/systemd/system/camera-snapshot.service
```

İçerik:

```ini
[Unit]
Description=Carrefoursa Camera Snapshot System
After=network.target postgresql.service

[Service]
Type=simple
User=your-username
WorkingDirectory=/opt/carrefoursa-kamera
Environment="PATH=/opt/carrefoursa-kamera/venv/bin"
ExecStart=/opt/carrefoursa-kamera/venv/bin/python /opt/carrefoursa-kamera/multi_camera_system/camera_snapshot_system.py
Restart=always
RestartSec=10
StandardOutput=append:/opt/carrefoursa-kamera/logs/camera-snapshot.log
StandardError=append:/opt/carrefoursa-kamera/logs/camera-snapshot-error.log

[Install]
WantedBy=multi-user.target
```

#### API Service (Manav Analiz API)

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
User=your-username
WorkingDirectory=/opt/carrefoursa-kamera/doluluk&reyonsıralaması/manav_analiz
Environment="PATH=/opt/carrefoursa-kamera/venv/bin"
ExecStart=/opt/carrefoursa-kamera/venv/bin/uvicorn main:app --host 0.0.0.0 --port 8000
Restart=always
RestartSec=10
StandardOutput=append:/opt/carrefoursa-kamera/logs/manav-api.log
StandardError=append:/opt/carrefoursa-kamera/logs/manav-api-error.log

[Install]
WantedBy=multi-user.target
```

#### Batch Processor Service

```bash
sudo nano /etc/systemd/system/batch-processor.service
```

İçerik:

```ini
[Unit]
Description=Batch Processor Service
After=network.target postgresql.service manav-api.service

[Service]
Type=simple
User=your-username
WorkingDirectory=/opt/carrefoursa-kamera/doluluk&reyonsıralaması/manav_analiz
Environment="PATH=/opt/carrefoursa-kamera/venv/bin"
ExecStart=/opt/carrefoursa-kamera/venv/bin/python /opt/carrefoursa-kamera/doluluk&reyonsıralaması/manav_analiz/batch_processor.py
Restart=always
RestartSec=30
StandardOutput=append:/opt/carrefoursa-kamera/logs/batch-processor.log
StandardError=append:/opt/carrefoursa-kamera/logs/batch-processor-error.log

[Install]
WantedBy=multi-user.target
```

### 2. Servisleri Başlatma

```bash
# Systemd'yi yeniden yükle
sudo systemctl daemon-reload

# Servisleri etkinleştir (otomatik başlatma için)
sudo systemctl enable camera-snapshot.service
sudo systemctl enable manav-api.service
sudo systemctl enable batch-processor.service

# Servisleri başlat
sudo systemctl start camera-snapshot.service
sudo systemctl start manav-api.service
sudo systemctl start batch-processor.service

# Durumlarını kontrol et
sudo systemctl status camera-snapshot.service
sudo systemctl status manav-api.service
sudo systemctl status batch-processor.service
```

### 3. Cron Job (Zamanlanmış Görevler)

Eğer snapshot sistemini belirli saatlerde çalıştırmak istiyorsanız:

```bash
# Crontab'ı düzenle
crontab -e

# Örnek: Her gün saat 08:00'de snapshot al
0 8 * * * cd /opt/carrefoursa-kamera && source venv/bin/activate && python multi_camera_system/camera_snapshot_system.py >> logs/cron-snapshot.log 2>&1

# Örnek: Her saat başı snapshot al
0 * * * * cd /opt/carrefoursa-kamera && source venv/bin/activate && python multi_camera_system/camera_snapshot_system.py >> logs/cron-snapshot.log 2>&1
```

---

## 📊 İzleme ve Loglar

### Log Dosyaları

```bash
# Log dizinini oluştur
mkdir -p /opt/carrefoursa-kamera/logs

# Log dosyalarını izle
tail -f /opt/carrefoursa-kamera/logs/camera-snapshot.log
tail -f /opt/carrefoursa-kamera/logs/manav-api.log
tail -f /opt/carrefoursa-kamera/logs/batch-processor.log

# Tüm logları izle
tail -f /opt/carrefoursa-kamera/logs/*.log
```

### Servis Durumlarını Kontrol Etme

```bash
# Tüm servislerin durumunu kontrol et
sudo systemctl status camera-snapshot.service
sudo systemctl status manav-api.service
sudo systemctl status batch-processor.service

# Servisleri yeniden başlat
sudo systemctl restart camera-snapshot.service
sudo systemctl restart manav-api.service
sudo systemctl restart batch-processor.service

# Servisleri durdur
sudo systemctl stop camera-snapshot.service
sudo systemctl stop manav-api.service
sudo systemctl stop batch-processor.service
```

### API Health Check

```bash
# API'nin çalışıp çalışmadığını kontrol et
curl http://localhost:8000/health

# API bilgilerini görüntüle
curl http://localhost:8000/
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
ls -la /opt/carrefoursa-kamera

# Gerekirse sahiplik değiştir
sudo chown -R $USER:$USER /opt/carrefoursa-kamera
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
python3 -c "import psycopg2; conn = psycopg2.connect('postgresql://grocerryadmin:a08Iyr95vLHTYY@45.84.18.76:5432/grocerryadmin'); print('Bağlantı başarılı!')"
```

### 6. S3 Bağlantı Sorunları

```bash
# S3 bağlantısını test et
source venv/bin/activate
python3 -c "
import boto3
s3 = boto3.client('s3',
    endpoint_url='https://161cohesity.carrefoursa.com:3000',
    aws_access_key_id='sWxdTl3ERx7myBE1qpW06_haVvuhATcdsmBbqaWkXYU',
    aws_secret_access_key='Ti9Fonk3wYyG5PMx5LaGUmlcVyCuqsE5BLVV5vv8PU0',
    verify=False
)
print('S3 bağlantısı başarılı!')
print('Buckets:', s3.list_buckets())
"
```

---

## 📝 Hızlı Başlangıç Özeti

```bash
# 1. Projeyi kopyala
cd /opt
sudo mkdir -p carrefoursa-kamera
sudo chown $USER:$USER carrefoursa-kamera
cd carrefoursa-kamera
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

# 5. Systemd service dosyalarını oluştur
sudo nano /etc/systemd/system/camera-snapshot.service
sudo nano /etc/systemd/system/manav-api.service
sudo nano /etc/systemd/system/batch-processor.service
# Yukarıdaki service içeriklerini yapıştır

# 6. Servisleri başlat
sudo systemctl daemon-reload
sudo systemctl enable camera-snapshot manav-api batch-processor
sudo systemctl start camera-snapshot manav-api batch-processor

# 7. Durumları kontrol et
sudo systemctl status camera-snapshot
sudo systemctl status manav-api
sudo systemctl status batch-processor
```

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

