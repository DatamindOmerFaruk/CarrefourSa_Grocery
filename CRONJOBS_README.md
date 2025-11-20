# Cronjob Kurulum Rehberi

Bu rehber, tüm `.sh` script'lerinin otomatik olarak çalışması için cronjob'ların nasıl kurulacağını açıklar.

## 📋 Kurulum Adımları

### 1. Script Dosyalarını Oluşturun

Önce aşağıdaki script dosyalarının oluşturulduğundan emin olun:

- `run_camera_snapshot.sh` - Kamera snapshot sistemi
- `run_batch_processor.sh` - Batch işlemci
- `run_ptz_analysis.sh` - PTZ analiz servisi

Bu script'lerin oluşturulması için `DEPLOYMENT.md` dosyasındaki "Wrapper Script'ler" bölümüne bakın.

### 2. Cronjob Kurulum Script'ini Çalıştırın

```bash
# Script'e çalıştırma izni verin
chmod +x setup_cronjobs.sh

# Script'i çalıştırın
./setup_cronjobs.sh
```

Script otomatik olarak:
- Mevcut crontab'ı yedekler
- Tüm script dosyalarını kontrol eder
- Cronjob'ları ekler
- Log dizinini oluşturur

### 3. Kurulum Sonrası Kontrol

```bash
# Cronjob'ları listelemek için
crontab -l

# Belirli bir cronjob'u görmek için
crontab -l | grep "camera_snapshot"
crontab -l | grep "batch_processor"
crontab -l | grep "ptz_analysis"
```

## ⏰ Varsayılan Zamanlama

Script, aşağıdaki zamanlarda cronjob'ları kurar:

| Script | Zaman | Açıklama |
|--------|-------|----------|
| `run_camera_snapshot.sh` | Her saat başı (9:00-21:00) | `0 9-21 * * *` |
| `run_batch_processor.sh` | Her saat 30'da (9:30-21:30) | `30 9-21 * * *` |
| `run_ptz_analysis.sh` | Her saat 30'da (9:30-21:30) | `30 9-21 * * *` |

## 🔧 Zamanlamayı Değiştirme

Eğer farklı saatlerde çalışmasını istiyorsanız:

```bash
# Crontab'ı düzenle
crontab -e

# İlgili satırları bulun ve değiştirin
# Örnek: Her 30 dakikada bir çalıştırmak için
# */30 9-21 * * * /path/to/script.sh
```

### Cron Format Açıklaması

```
* * * * * komut
│ │ │ │ │
│ │ │ │ └─── Haftanın günü (0-7, 0 ve 7 = Pazar)
│ │ │ └───── Ay (1-12)
│ │ └─────── Ayın günü (1-31)
│ └───────── Saat (0-23)
└─────────── Dakika (0-59)
```

### Örnek Zamanlamalar

```bash
# Her 15 dakikada bir
*/15 * * * * /path/to/script.sh

# Her gün saat 08:00'de
0 8 * * * /path/to/script.sh

# Hafta içi (Pazartesi-Cuma) saat 09:00-17:00 arası her saat başı
0 9-17 * * 1-5 /path/to/script.sh

# Her gün saat 00:00'da
0 0 * * * /path/to/script.sh
```

## 📊 Log Dosyaları

Tüm cronjob çıktıları aşağıdaki log dosyalarına yazılır:

- `logs/cron-snapshot.log` - Camera snapshot logları
- `logs/cron-batch.log` - Batch processor logları
- `logs/cron-ptz-analysis.log` - PTZ analysis logları

### Log Dosyalarını İzleme

```bash
# Son 50 satırı görmek için
tail -n 50 logs/cron-snapshot.log

# Canlı izlemek için
tail -f logs/cron-snapshot.log

# Tüm log dosyalarını görmek için
ls -lh logs/cron-*.log
```

## 🗑️ Cronjob'ları Kaldırma

### Tüm Cronjob'ları Kaldırma

```bash
# Crontab'ı düzenle
crontab -e

# "Carrefoursa Kamera Entegrasyon Cronjobs" bölümünü bulun
# İlgili satırları silin veya başına # ekleyin
```

### Belirli Bir Cronjob'u Kaldırma

```bash
# Crontab'ı düzenle
crontab -e

# İlgili satırı bulun ve silin
# Örnek: run_camera_snapshot.sh satırını silmek için
# 0 9-21 * * * /path/to/run_camera_snapshot.sh ... satırını silin
```

### Tüm Crontab'ı Temizleme

```bash
# DİKKAT: Bu komut tüm cronjob'ları siler!
crontab -r

# Yedekten geri yüklemek için
crontab /path/to/backup_file.txt
```

## 🔍 Sorun Giderme

### Cronjob Çalışmıyor

1. **Cron servisinin çalıştığını kontrol edin:**
   ```bash
   sudo systemctl status cron
   # veya
   sudo systemctl status crond
   ```

2. **Cronjob'ların doğru kurulduğunu kontrol edin:**
   ```bash
   crontab -l
   ```

3. **Log dosyalarını kontrol edin:**
   ```bash
   tail -f logs/cron-*.log
   ```

4. **Script'lerin çalıştırma izni olduğunu kontrol edin:**
   ```bash
   ls -l run_*.sh
   # Tüm script'ler -rwxr-xr-x olmalı
   ```

5. **Manuel olarak script'i çalıştırın:**
   ```bash
   ./run_camera_snapshot.sh
   # Hata mesajlarını kontrol edin
   ```

### Yol Sorunları

Eğer cronjob'lar "command not found" hatası veriyorsa, script'lerde tam yol kullanın:

```bash
# Crontab'da tam yol kullanın
0 9-21 * * * /data/carrefoursa-kamera/CarrefourSa_Grocery/run_camera_snapshot.sh
```

### Environment Variables

Cronjob'lar, kullanıcı ortam değişkenlerini yüklemeyebilir. Script'lerinizde `.env` dosyasını doğrudan yükleyin:

```bash
#!/bin/bash
cd /path/to/project
source venv/bin/activate
# .env dosyası otomatik yüklenir
```

## 📝 Yedekleme

Cronjob kurulum script'i, mevcut crontab'ı otomatik olarak yedekler:

```bash
# Yedek dosyaları görmek için
ls -lh logs/crontab_backup_*.txt

# Yedekten geri yüklemek için
crontab logs/crontab_backup_YYYYMMDD_HHMMSS.txt
```

## ✅ Kontrol Listesi

Kurulum sonrası kontrol edilmesi gerekenler:

- [ ] Tüm script dosyaları oluşturuldu (`run_*.sh`)
- [ ] Script'lere çalıştırma izni verildi (`chmod +x`)
- [ ] Cronjob'lar kuruldu (`crontab -l`)
- [ ] Log dizini oluşturuldu (`logs/`)
- [ ] Cron servisi çalışıyor (`systemctl status cron`)
- [ ] Test çalıştırması yapıldı (manuel script çalıştırma)

## 🆘 Yardım

Sorun yaşıyorsanız:

1. Log dosyalarını kontrol edin
2. Manuel script çalıştırmayı deneyin
3. `DEPLOYMENT.md` dosyasındaki "Sorun Giderme" bölümüne bakın

