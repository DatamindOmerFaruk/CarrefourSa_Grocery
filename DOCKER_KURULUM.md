# 🐳 Docker ile Linux Sunucu Kurulum Rehberi

Bu rehber, projenizi Docker kullanarak Linux sunucuda adım adım nasıl kuracağınızı ve çalıştıracağınızı gösterir.

---

## 📋 Adım 1: Docker Kurulumu

### Ubuntu/Debian için:

```bash
# 1. Eski Docker versiyonlarını kaldır (varsa)
sudo apt-get remove docker docker-engine docker.io containerd runc

# 2. Gerekli paketleri yükle
sudo apt-get update
sudo apt-get install -y \
    ca-certificates \
    curl \
    gnupg \
    lsb-release

# 3. Docker'ın resmi GPG key'ini ekle
sudo mkdir -p /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/ubuntu/gpg | sudo gpg --dearmor -o /etc/apt/keyrings/docker.gpg

# 4. Docker repository'yi ekle
echo \
  "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/ubuntu \
  $(lsb_release -cs) stable" | sudo tee /etc/apt/sources.list.d/docker.list > /dev/null

# 5. Docker'ı yükle
sudo apt-get update
sudo apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin

# 6. Docker'ı başlat ve otomatik başlatmayı etkinleştir
sudo systemctl start docker
sudo systemctl enable docker

# 7. Kullanıcıyı docker grubuna ekle (sudo olmadan çalıştırmak için)
sudo usermod -aG docker $USER

# 8. Yeni grubu aktif et (veya logout/login yapın)
newgrp docker

# 9. Docker kurulumunu test et
docker --version
docker compose version
docker run hello-world
```

**✅ Kontrol:** Yukarıdaki komutlar hatasız çalıştıysa Docker kurulmuştur.

---

## 📦 Adım 2: Projeyi Sunucuya Kopyalama

### Seçenek 1: SCP ile (Windows'tan)

```bash
# Windows PowerShell veya CMD'de:
scp -r "C:\Users\test\Desktop\Carrefoursa\reyon\Kamera Entegrasyon" user@sunucu-ip:/opt/carrefoursa-kamera
```

### Seçenek 2: Git ile (eğer repository varsa)

```bash
# Sunucuda:
cd /opt
sudo mkdir -p carrefoursa-kamera
sudo chown $USER:$USER carrefoursa-kamera
cd carrefoursa-kamera
git clone <repository-url> .
```

### Seçenek 3: Manuel Kopyalama

```bash
# Sunucuda dizin oluştur
sudo mkdir -p /opt/carrefoursa-kamera
sudo chown $USER:$USER /opt/carrefoursa-kamera

# Sonra WinSCP, FileZilla gibi bir araçla dosyaları kopyalayın
```

**✅ Kontrol:** Proje dosyaları `/opt/carrefoursa-kamera` dizininde olmalı.

---

## ⚙️ Adım 3: Konfigürasyon Dosyalarını Hazırlama

### 3.1. .env Dosyası Oluşturma

```bash
# Proje dizinine git
cd /opt/carrefoursa-kamera

# .env dosyası oluştur
nano .env
```

`.env` dosyasına şu içeriği yapıştırın:

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
AZURE_OPENAI_API_KEY=your-api-key-here
AZURE_OPENAI_DEPLOYMENT=gpt-4.1
AZURE_API_VERSION=2024-06-01

# Azure Storage (Batch Processor için - eğer kullanılıyorsa)
AZURE_STORAGE_CONNECTION_STRING=DefaultEndpointsProtocol=https;AccountName=...;AccountKey=...
AZURE_CONTAINER_NAME=snapshot
AZURE_SAS_TOKEN=your-sas-token-here

# API Ayarları
API_BASE_URL=http://manav-api:8000
BATCH_SIZE=10
RETRY_COUNT=3
REQUEST_DELAY=1.0

# Diğer Ayarlar
MIN_CONF_ROTTEN=0.85
COLLAGE_FONT=
TEST_MODE=false
```

**💾 Kaydet:** `Ctrl+O` (kaydet), `Enter` (onayla), `Ctrl+X` (çık)

**✅ Kontrol:** `.env` dosyası oluşturuldu mu?
```bash
ls -la .env
cat .env  # İçeriği kontrol et
```

### 3.2. Gerekli Dizinleri Oluşturma

```bash
# Dizinleri oluştur
mkdir -p snapshots crops logs

# İzinleri ayarla
chmod 755 snapshots crops logs
```

**✅ Kontrol:**
```bash
ls -ld snapshots crops logs
```

### 3.3. Kamera Konfigürasyon Dosyalarını Kontrol Etme

```bash
# Konfigürasyon dosyalarının varlığını kontrol et
ls -lh multi_camera_system/cameras.yaml
ls -lh multi_camera_system/cameras_reyon_genel.yaml

# İçeriklerini kontrol et (gerekirse düzenle)
nano multi_camera_system/cameras.yaml
```

---

## 🏗️ Adım 4: Docker Image'larını Build Etme

```bash
# Proje dizininde olduğunuzdan emin olun
cd /opt/carrefoursa-kamera

# Tüm Docker image'larını build et (bu işlem 5-10 dakika sürebilir)
docker compose build

# Build işlemini izle - her servis için "Successfully built" mesajını görmelisiniz
```

**✅ Kontrol:** Build başarılı mı?
```bash
# Image'ları listele
docker images | grep carrefoursa

# Şunları görmelisiniz:
# - carrefoursa-kamera-camera-snapshot
# - carrefoursa-kamera-manav-api
# - carrefoursa-kamera-batch-processor
```

**⚠️ Sorun:** Build sırasında hata alırsanız:
```bash
# Detaylı logları görüntüle
docker compose build --progress=plain

# Belirli bir servisi tekrar build et
docker compose build camera-snapshot
```

---

## 🚀 Adım 5: Servisleri Başlatma

### 5.1. Tüm Servisleri Başlat

```bash
# Tüm servisleri arka planda başlat
docker compose up -d

# Başlatma işlemini izle
docker compose ps
```

**✅ Kontrol:** Tüm container'lar "Up" durumunda olmalı:
```bash
docker compose ps

# Çıktı örneği:
# NAME                          STATUS
# carrefoursa-camera-snapshot   Up
# carrefoursa-manav-api         Up
# carrefoursa-batch-processor   Up
```

### 5.2. Logları Kontrol Etme

```bash
# Tüm servislerin loglarını görüntüle
docker compose logs

# Canlı log takibi (Ctrl+C ile çıkış)
docker compose logs -f

# Belirli bir servisin logları
docker compose logs -f camera-snapshot
docker compose logs -f manav-api
docker compose logs -f batch-processor
```

**✅ Kontrol:** Hata mesajı var mı?
```bash
# Son 50 satır log
docker compose logs --tail=50

# Sadece hataları filtrele
docker compose logs | grep -i error
```

---

## 🔍 Adım 6: Servisleri Test Etme

### 6.1. API Health Check

```bash
# API'nin çalışıp çalışmadığını kontrol et
curl http://localhost:8000/health

# Veya tarayıcıda aç:
# http://sunucu-ip:8000/health
```

**✅ Beklenen Çıktı:**
```json
{
  "status": "healthy",
  "azure_openai_configured": true,
  "deployment": "gpt-4.1",
  ...
}
```

### 6.2. API Ana Sayfası

```bash
curl http://localhost:8000/
```

### 6.3. Container Durumları

```bash
# Detaylı durum bilgisi
docker compose ps

# Container istatistikleri (kaynak kullanımı)
docker stats --no-stream
```

---

## 📊 Adım 7: Servisleri Yönetme

### Servisleri Durdurma

```bash
# Tüm servisleri durdur
docker compose down

# Servisleri durdur ama container'ları silme
docker compose stop
```

### Servisleri Yeniden Başlatma

```bash
# Tüm servisleri yeniden başlat
docker compose restart

# Belirli bir servisi yeniden başlat
docker compose restart camera-snapshot
```

### Servisleri Güncelleme (Kod Değişikliğinden Sonra)

```bash
# 1. Yeni kodu kopyala (veya git pull)

# 2. Image'ları yeniden build et
docker compose build

# 3. Servisleri yeniden başlat
docker compose up -d

# 4. Logları kontrol et
docker compose logs -f
```

---

## 🔧 Adım 8: Sorun Giderme

### Container Başlamıyor

```bash
# Container loglarını kontrol et
docker compose logs camera-snapshot

# Container'ın detaylı durumunu görüntüle
docker inspect carrefoursa-camera-snapshot

# Container'ı yeniden başlat
docker compose restart camera-snapshot
```

### Port Çakışması

```bash
# Port 8000'in kullanımda olup olmadığını kontrol et
sudo netstat -tulpn | grep 8000

# Eğer kullanılıyorsa, docker-compose.yml'de portu değiştir:
# ports:
#   - "8001:8000"  # Host port 8001, container port 8000
```

### Environment Variables Sorunları

```bash
# Container içindeki environment variables'ları kontrol et
docker compose exec camera-snapshot env

# .env dosyasını kontrol et
cat .env
```

### Disk Alanı Sorunları

```bash
# Docker disk kullanımını kontrol et
docker system df

# Kullanılmayan kaynakları temizle
docker system prune -a
```

### Network Sorunları

```bash
# Container'ların birbirine erişip erişemediğini test et
docker compose exec batch-processor ping manav-api

# Network'leri listele
docker network ls
```

---

## 📝 Özet: Tüm Komutlar

```bash
# ============================================
# KURULUM
# ============================================

# 1. Docker kur (sadece ilk kurulumda)
sudo apt-get update
sudo apt-get install -y docker.io docker-compose
sudo systemctl start docker
sudo systemctl enable docker
sudo usermod -aG docker $USER
newgrp docker

# 2. Projeyi kopyala
cd /opt/carrefoursa-kamera

# 3. .env dosyası oluştur
nano .env  # Yukarıdaki içeriği yapıştır

# 4. Dizinleri oluştur
mkdir -p snapshots crops logs

# 5. Build et
docker compose build

# 6. Başlat
docker compose up -d

# ============================================
# GÜNLÜ KULLANIM
# ============================================

# Logları izle
docker compose logs -f

# Durumları kontrol et
docker compose ps

# Yeniden başlat
docker compose restart

# Durdur
docker compose down

# Güncelleme
docker compose build
docker compose up -d
```

---

## 🎯 Hızlı Kontrol Listesi

Kurulumun başarılı olduğunu kontrol etmek için:

- [ ] Docker kurulu ve çalışıyor (`docker --version`)
- [ ] Proje dosyaları sunucuda (`ls /opt/carrefoursa-kamera`)
- [ ] .env dosyası oluşturuldu (`cat .env`)
- [ ] Dizinler oluşturuldu (`ls -d snapshots crops logs`)
- [ ] Image'lar build edildi (`docker images | grep carrefoursa`)
- [ ] Container'lar çalışıyor (`docker compose ps`)
- [ ] API erişilebilir (`curl http://localhost:8000/health`)
- [ ] Loglar hatasız (`docker compose logs | grep -i error`)

---

## 📞 Yardım

Sorun yaşarsanız:

1. **Logları kontrol edin:**
   ```bash
   docker compose logs --tail=100
   ```

2. **Container durumlarını kontrol edin:**
   ```bash
   docker compose ps -a
   ```

3. **Environment variables'ları kontrol edin:**
   ```bash
   docker compose exec camera-snapshot env | grep -E "S3_|PG_|AZURE_"
   ```

4. **Network bağlantısını test edin:**
   ```bash
   docker compose exec camera-snapshot ping -c 3 45.84.18.76
   ```

---

## 🎉 Başarılı!

Tüm adımlar tamamlandıysa, sisteminiz çalışıyor demektir! 

- **API:** http://sunucu-ip:8000
- **Loglar:** `docker compose logs -f`
- **Durum:** `docker compose ps`

