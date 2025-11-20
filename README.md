# Carrefoursa Kamera Entegrasyon Sistemi

Multi-camera snapshot sistemi, manav analiz API'si ve batch processor.

## 📚 Dokümantasyon

**Tüm kurulum adımları, anlatımlar ve detaylı bilgiler için:**
👉 **[DEPLOYMENT.md](DEPLOYMENT.md)** dosyasına bakın.

## 🚀 Hızlı Başlangıç

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

# 4. Servisleri başlat
sudo systemctl enable manav-api
sudo systemctl start manav-api
```

Detaylı kurulum için `DEPLOYMENT.md` dosyasına bakın.
