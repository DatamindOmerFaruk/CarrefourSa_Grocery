# Carrefoursa Kamera Entegrasyon Sistemi

Multi-camera snapshot sistemi, manav analiz API'si ve batch processor.

## 🚀 Hızlı Başlangıç (Docker ile)

### Linux Sunucuda Kurulum

```bash
# 1. Docker kur (sadece ilk kurulumda)
sudo apt-get update
sudo apt-get install -y docker.io docker-compose
sudo systemctl start docker
sudo systemctl enable docker
sudo usermod -aG docker $USER
newgrp docker

# 2. Projeyi kopyala
cd /opt
sudo mkdir -p carrefoursa-kamera
sudo chown $USER:$USER carrefoursa-kamera
cd carrefoursa-kamera
# Proje dosyalarını buraya kopyala

# 3. .env dosyası oluştur
nano .env
# Aşağıdaki içeriği yapıştır ve düzenle

# 4. Dizinleri oluştur
mkdir -p snapshots crops logs

# 5. Build ve başlat
docker compose build
docker compose up -d

# 6. Logları izle
docker compose logs -f
```

### .env Dosyası İçeriği

```bash
# S3 Object Storage
S3_ENDPOINT_URL=https://161cohesity.carrefoursa.com:3000
S3_ACCESS_KEY_ID=your_access_key
S3_SECRET_ACCESS_KEY=your_secret_key
S3_BUCKET_NAME=Grocery

# PostgreSQL
PG_HOST=45.84.18.76
PG_PORT=5432
PG_USER=grocerryadmin
PG_PASSWORD=a08Iyr95vLHTYY
PG_DATABASE=grocerryadmin
PG_DSN=postgresql://grocerryadmin:a08Iyr95vLHTYY@45.84.18.76:5432/grocerryadmin

# Azure OpenAI
AZURE_OPENAI_ENDPOINT=https://your-endpoint.openai.azure.com/
AZURE_OPENAI_API_KEY=your-api-key
AZURE_OPENAI_DEPLOYMENT=gpt-4.1
AZURE_API_VERSION=2024-06-01

# API Ayarları
API_BASE_URL=http://manav-api:8000
```

## 📚 Detaylı Dokümantasyon

- **Docker Kurulum:** `DOCKER_KURULUM.md` - Adım adım Docker kurulum rehberi
- **Kod Açıklaması:** `multi_camera_system/KOD_ACIKLAMASI.md` - Kod detayları

## 🔧 Temel Komutlar

```bash
# Servisleri başlat
docker compose up -d

# Servisleri durdur
docker compose down

# Logları görüntüle
docker compose logs -f

# Durumları kontrol et
docker compose ps

# Yeniden başlat
docker compose restart
```

## 📖 Daha Fazla Bilgi

Detaylı kurulum ve kullanım için `DOCKER_KURULUM.md` dosyasına bakın.

