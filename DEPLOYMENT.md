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

---

## 🚀 Servisleri Başlatma

### Servisler Hakkında

Sistemde 4 ana servis bulunmaktadır:

#### 1. **Camera Snapshot System** (`camera_snapshot_system.py`)
- **Görevi**: PTZ kameralardan görüntü alır, YOLO ile insan tespiti yapar, geçerli görüntüleri S3 Object Storage'a yükler
- **Çalışma Şekli**: Cron job ile saatlik çalışır (09:00-21:00 arası, her saat başı)
- **Özellikler**:
  - Çoklu kamera desteği
  - İnsan tespiti ile kalite kontrolü
  - Otomatik retry mekanizması
  - S3'e otomatik yükleme
  - Lokal dosyaları S3'e yüklendikten sonra silme

#### 2. **Manav Analiz API** (`manav_analiz/main.py`)
- **Görevi**: FastAPI tabanlı REST API servisi. Görüntü analizi için endpoint'ler sağlar
- **Çalışma Şekli**: Systemd service olarak sürekli çalışır (7/24)
- **Özellikler**:
  - Content analizi endpoint'i
  - Stock analizi endpoint'i
  - Evaluation endpoint'i
  - Health check endpoint'i
  - Port: 8000
- **Not**: Batch Processor bu API'yi kullanıyorsa gerekli, aksi halde kaldırılabilir

#### 3. **Batch Processor** (`doluluk&reyonsıralaması/manav_analiz/batch_processor.py`)
- **Görevi**: S3'ten görüntüleri alır, Manav Analiz API'ye gönderir, sonuçları PostgreSQL'e kaydeder
- **Çalışma Şekli**: Cron job ile saatlik çalışır (09:30-21:30 arası, camera-snapshot'tan 30 dakika sonra)
- **Özellikler**:
  - S3'ten görüntü listeleme
  - Batch işleme (toplu analiz)
  - API çağrıları (Content, Stock, Evaluation)
  - PostgreSQL'e sonuç kaydetme
  - Retry mekanizması
  - İki mod: Tam analiz veya sadece stock analizi

#### 4. **PTZ Analysis Service** (3 ayrı script: `ptz_face_blur.py`, `ptz_yolo_llm_analysis.py`, `ptz_db_writer.py`)
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

### Servis Koordinasyonu

```
09:00 → Camera Snapshot çalışır → Görüntüler S3'e yüklenir
09:30 → Batch Processor çalışır → S3'ten görüntüleri alır, API'ye gönderir, DB'ye kaydeder
09:30 → PTZ Analysis Service çalışır → S3'ten snapshot'ları alır, YOLO+LLM analizi yapar, DB'ye kaydeder
10:00 → Camera Snapshot çalışır → Yeni görüntüler S3'e yüklenir
10:30 → Batch Processor çalışır → Yeni görüntüleri işler
10:30 → PTZ Analysis Service çalışır → Yeni snapshot'ları işler
...
21:00 → Camera Snapshot çalışır (son)
21:30 → Batch Processor çalışır (son)
21:30 → PTZ Analysis Service çalışır (son)

Manav API → 7/24 sürekli çalışır (systemd service) - Batch Processor tarafından kullanılıyorsa gerekli
```

**Önemli Notlar:**
- Camera Snapshot her saat başı çalışır (09:00, 10:00, ..., 21:00)
- Batch Processor ve PTZ Analysis Service her saatin 30. dakikasında çalışır (09:30, 10:30, ..., 21:30)
- Her iki analiz servisi de aynı S3 snapshot'larını kullanır ama farklı analiz yöntemleri uygular
- Batch Processor: API tabanlı analiz (doluluk ve reyon sıralaması için)
- PTZ Analysis Service: YOLO + LLM tabanlı analiz (çürük tespiti için)

### 1. Systemd Service Dosyası (Sadece Manav API)

Manav API sürekli çalışması gerektiği için systemd service olarak yapılandırılır:

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

### 2. Manav API Servisini Başlatma

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

### 3. PTZ Analysis Service Script'leri

Notebook kodları 3 ayrı Python script'e ayrılmıştır:

1. **`ptz_face_blur.py`** - Yüzlerin blur'lanması (Cell 1)
   - S3'ten snapshot'ları alır
   - Yüzleri tespit edip blur'lar
   - Tekrar S3'e yükler

2. **`ptz_yolo_llm_analysis.py`** - YOLO detection ve LLM analizi (Cell 2)
   - S3'ten snapshot'ları alır
   - YOLOv12 ile meyve/sebze tespiti yapar
   - Crop'ları oluşturur ve S3'e yükler
   - Collage'lar oluşturur
   - Azure OpenAI ile çürük tespiti yapar
   - Sonuçları `.llm.json` dosyalarına kaydeder ve S3'e yükler

3. **`ptz_db_writer.py`** - Veritabanına yazma (Cell 3)
   - S3'ten `.llm.json` dosyalarını okur
   - PostgreSQL veritabanına sonuçları yazar

**Not**: Bu script'ler proje içinde mevcuttur. Ek bir oluşturma işlemi gerekmez.

### 4. Wrapper Script'leri Oluşturma

Analiz servislerinin otomatik çalışması için wrapper script'ler oluşturun:

```bash
# Batch Processor wrapper script
cat > /data/carrefoursa-kamera/CarrefourSa_Grocery/run_batch_processor.sh << 'EOF'
#!/bin/bash
cd /data/carrefoursa-kamera/CarrefourSa_Grocery/doluluk\&reyonsıralaması/manav_analiz
source ../../venv/bin/activate
echo "2" | python batch_processor.py
EOF

chmod +x /data/carrefoursa-kamera/CarrefourSa_Grocery/run_batch_processor.sh

# PTZ Analysis Service wrapper script (3 script'i sırayla çalıştırır)
cat > /data/carrefoursa-kamera/CarrefourSa_Grocery/run_ptz_analysis.sh << 'EOF'
#!/bin/bash
cd /data/carrefoursa-kamera/CarrefourSa_Grocery
source venv/bin/activate

# 1. Yüz blur'lanması (opsiyonel, gerekirse açılabilir)
# python ptz_face_blur.py >> logs/cron-ptz-face-blur.log 2>&1

# 2. YOLO detection ve LLM analizi
echo "[$(date '+%Y-%m-%d %H:%M:%S')] PTZ YOLO + LLM Analysis başlatılıyor..."
python ptz_yolo_llm_analysis.py >> logs/cron-ptz-yolo-llm.log 2>&1
YOLO_EXIT_CODE=$?

if [ $YOLO_EXIT_CODE -eq 0 ]; then
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] PTZ YOLO + LLM Analysis tamamlandı"
    
    # 3. Veritabanına yazma
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] PTZ Database Writer başlatılıyor..."
    python ptz_db_writer.py >> logs/cron-ptz-db-writer.log 2>&1
    DB_EXIT_CODE=$?
    
    if [ $DB_EXIT_CODE -eq 0 ]; then
        echo "[$(date '+%Y-%m-%d %H:%M:%S')] PTZ Database Writer tamamlandı"
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

**Not**: `run_ptz_analysis.sh` script'i 3 aşamayı sırayla çalıştırır:
1. `ptz_face_blur.py` (şu an yorum satırı, gerekirse açılabilir)
2. `ptz_yolo_llm_analysis.py` (YOLO detection ve LLM analizi)
3. `ptz_db_writer.py` (veritabanına yazma)

Her aşama başarılı olursa bir sonraki aşamaya geçilir. Bir aşamada hata olursa işlem durdurulur.

### 5. Cron Job Yapılandırması

Tüm servisler için cron job'ları yapılandırın:

```bash
# Crontab'ı düzenle
crontab -e

# Aşağıdaki satırları ekle:

# Camera Snapshot: Her gün 09:00-21:00 arası her saat başı çalışır
0 9-21 * * * cd /data/carrefoursa-kamera/CarrefourSa_Grocery && source venv/bin/activate && python multi_camera_system/camera_snapshot_system.py >> logs/cron-snapshot.log 2>&1

# Batch Processor: Her gün 09:30-21:30 arası çalışır (camera-snapshot'tan 30 dakika sonra)
30 9-21 * * * /data/carrefoursa-kamera/CarrefourSa_Grocery/run_batch_processor.sh >> /data/carrefoursa-kamera/CarrefourSa_Grocery/logs/cron-batch.log 2>&1

# PTZ Analysis Service: Her gün 09:30-21:30 arası çalışır (camera-snapshot'tan 30 dakika sonra)
30 9-21 * * * /data/carrefoursa-kamera/CarrefourSa_Grocery/run_ptz_analysis.sh >> /data/carrefoursa-kamera/CarrefourSa_Grocery/logs/cron-ptz-analysis.log 2>&1
```

### 6. Cron Job'ları Kontrol Etme

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

# 5. Manav API systemd service dosyasını oluştur
sudo nano /etc/systemd/system/manav-api.service
# Yukarıdaki manav-api service içeriğini yapıştır

# 6. Manav API servisini başlat
sudo systemctl daemon-reload
sudo systemctl enable manav-api.service
sudo systemctl start manav-api.service

# 7. PTZ Analysis Service script'leri kontrol et (notebook kodlarından oluşturulmuş)
# ptz_face_blur.py, ptz_yolo_llm_analysis.py, ptz_db_writer.py dosyaları mevcut olmalı
ls -lh ptz_*.py

# 8. Wrapper script'leri oluştur
# run_batch_processor.sh ve run_ptz_analysis.sh script'lerini oluştur (yukarıdaki örneklere göre)

# 9. Cron job'ları yapılandır
crontab -e
# Aşağıdaki satırları ekle:
# 0 9-21 * * * cd /data/carrefoursa-kamera/CarrefourSa_Grocery && source venv/bin/activate && python multi_camera_system/camera_snapshot_system.py >> logs/cron-snapshot.log 2>&1
# 30 9-21 * * * /data/carrefoursa-kamera/CarrefourSa_Grocery/run_batch_processor.sh >> /data/carrefoursa-kamera/CarrefourSa_Grocery/logs/cron-batch.log 2>&1
# 30 9-21 * * * /data/carrefoursa-kamera/CarrefourSa_Grocery/run_ptz_analysis.sh >> /data/carrefoursa-kamera/CarrefourSa_Grocery/logs/cron-ptz-analysis.log 2>&1

# 10. Durumları kontrol et
sudo systemctl status manav-api
crontab -l
```

## ⚠️ Önemli Notlar

### 1. PTZ Analysis Service Script'leri

`ptz_snapshot_notebook.ipynb` dosyasındaki kodlar 3 ayrı Python script'e çevrilmiştir:

- **`ptz_face_blur.py`** - Cell 1 kodları (Yüz blur'lanması, opsiyonel)
- **`ptz_yolo_llm_analysis.py`** - Cell 2 kodları (YOLO detection + cropping + collage + LLM analizi)
- **`ptz_db_writer.py`** - Cell 3 kodları (Veritabanına yazma)

Bu script'ler proje içinde mevcuttur ve `run_ptz_analysis.sh` wrapper script'i tarafından sırayla çalıştırılır.

### 2. Silinmesi Gereken Servisler

**Şu anda silinmesi gereken servis yok.** Tüm servisler kullanılıyor:
- **Manav API**: Batch Processor tarafından kullanılıyor (gerekli)
- **Camera Snapshot**: Görüntü çekme için gerekli
- **Batch Processor**: Doluluk ve reyon sıralaması analizi için gerekli
- **PTZ Analysis Service**: Çürük tespiti analizi için gerekli (3 ayrı script olarak mevcut)

### 3. Servis Bağımlılıkları

- **Manav API** → Batch Processor tarafından kullanılıyor (7/24 çalışmalı)
- **Camera Snapshot** → Batch Processor ve PTZ Analysis Service tarafından kullanılıyor (S3'e görüntü yükler)
- **Batch Processor** → Manav API'ye bağımlı (API çalışmalı)
- **PTZ Analysis Service** → Bağımsız çalışır (sadece S3 ve PostgreSQL'e bağlanır)

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

