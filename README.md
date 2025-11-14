# Carrefoursa Kamera Entegrasyon Sistemi

Multi-camera snapshot sistemi, manav analiz API'si ve batch processor.

## 🚀 Hızlı Başlangıç

### Linux Sunucuda Kurulum

```bash
# 1. Projeyi kopyala
cd /opt
sudo mkdir -p carrefoursa-kamera
sudo chown $USER:$USER carrefoursa-kamera
cd carrefoursa-kamera
# Proje dosyalarını buraya kopyala

# 2. Kurulum script'ini çalıştır
sudo bash install.sh

# 3. .env dosyası oluştur
nano .env
# DEPLOYMENT.md'deki .env içeriğini yapıştır

# 4. Servisleri başlat (eğer systemd kullanıyorsanız)
sudo systemctl enable camera-snapshot manav-api batch-processor
sudo systemctl start camera-snapshot manav-api batch-processor
```

## 📚 Detaylı Dokümantasyon

- **Kurulum Rehberi:** `DEPLOYMENT.md` - Adım adım Linux kurulum rehberi
- **Kod Açıklaması:** `multi_camera_system/KOD_ACIKLAMASI.md` - Kod detayları

## 🔧 Temel Komutlar

```bash
# Virtual environment'ı aktif et
source venv/bin/activate

# Camera Snapshot System
python multi_camera_system/camera_snapshot_system.py

# Manav Analiz API
cd doluluk&reyonsıralaması/manav_analiz
uvicorn main:app --host 0.0.0.0 --port 8000

# Batch Processor
python batch_processor.py
```

## 📖 Daha Fazla Bilgi

Detaylı kurulum ve kullanım için `DEPLOYMENT.md` dosyasına bakın.

