#!/bin/bash
# Cronjob Teşhis ve Kontrol Script'i
# Bu script, cron job'ların neden çalışmadığını tespit eder

set -e

# Renkli çıktı için
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

echo -e "${BLUE}========================================${NC}"
echo -e "${BLUE}Cronjob Teşhis ve Kontrol Script'i${NC}"
echo -e "${BLUE}========================================${NC}"
echo ""

# Proje dizinini bul
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
PROJECT_DIR="$SCRIPT_DIR"

# Eğer /data/carrefoursa-kamera/CarrefourSa_Grocery dizini varsa onu kullan
if [ -d "/data/carrefoursa-kamera/CarrefourSa_Grocery" ]; then
    PROJECT_DIR="/data/carrefoursa-kamera/CarrefourSa_Grocery"
    echo -e "${GREEN}✅ Proje dizini bulundu: $PROJECT_DIR${NC}"
else
    echo -e "${YELLOW}⚠️  /data/carrefoursa-kamera/CarrefourSa_Grocery bulunamadı${NC}"
    echo -e "${YELLOW}   Mevcut dizin kullanılacak: $PROJECT_DIR${NC}"
fi

echo ""

# 1. Cron servisinin çalışıp çalışmadığını kontrol et
echo -e "${BLUE}[1/8] Cron Servisi Kontrolü${NC}"
if systemctl is-active --quiet cron 2>/dev/null || systemctl is-active --quiet crond 2>/dev/null; then
    echo -e "${GREEN}✅ Cron servisi çalışıyor${NC}"
    CRON_SERVICE=$(systemctl is-active cron 2>/dev/null && echo "cron" || echo "crond")
    echo -e "   Servis adı: $CRON_SERVICE"
else
    echo -e "${RED}❌ Cron servisi çalışmıyor!${NC}"
    echo -e "${YELLOW}   Çözüm: sudo systemctl start cron${NC}"
    echo -e "${YELLOW}   veya: sudo systemctl start crond${NC}"
fi
echo ""

# 2. Crontab'ın kurulu olup olmadığını kontrol et
echo -e "${BLUE}[2/8] Crontab Kontrolü${NC}"
if crontab -l > /dev/null 2>&1; then
    CRON_COUNT=$(crontab -l | grep -c "Carrefoursa Kamera" || echo "0")
    if [ "$CRON_COUNT" -gt 0 ]; then
        echo -e "${GREEN}✅ Crontab kurulu ve Carrefoursa cronjob'ları bulundu${NC}"
        echo -e "   Bulunan cronjob sayısı: $CRON_COUNT"
        echo ""
        echo -e "${CYAN}Kurulu Cronjob'lar:${NC}"
        crontab -l | grep -A 1 "Carrefoursa Kamera" | grep -v "^#" | grep -v "^$" | while read line; do
            if [ ! -z "$line" ]; then
                echo -e "   ${YELLOW}$line${NC}"
            fi
        done
    else
        echo -e "${YELLOW}⚠️  Crontab var ama Carrefoursa cronjob'ları bulunamadı${NC}"
        echo -e "${YELLOW}   Çözüm: ./setup_cronjobs.sh çalıştırın${NC}"
    fi
else
    echo -e "${RED}❌ Crontab bulunamadı!${NC}"
    echo -e "${YELLOW}   Çözüm: ./setup_cronjobs.sh çalıştırın${NC}"
fi
echo ""

# 3. Script dosyalarının varlığını kontrol et
echo -e "${BLUE}[3/8] Script Dosyaları Kontrolü${NC}"
SCRIPTS=("run_camera_snapshot.sh" "run_batch_processor.sh" "run_ptz_analysis.sh")
MISSING_SCRIPTS=()

for script in "${SCRIPTS[@]}"; do
    if [ -f "$PROJECT_DIR/$script" ]; then
        echo -e "${GREEN}✅ $script bulundu${NC}"
    else
        echo -e "${RED}❌ $script bulunamadı!${NC}"
        MISSING_SCRIPTS+=("$script")
    fi
done

if [ ${#MISSING_SCRIPTS[@]} -gt 0 ]; then
    echo ""
    echo -e "${YELLOW}⚠️  Eksik script'ler: ${MISSING_SCRIPTS[*]}${NC}"
    echo -e "${YELLOW}   Çözüm: DEPLOYMENT.md dosyasındaki 'Wrapper Script'ler' bölümüne bakın${NC}"
fi
echo ""

# 4. Script'lerin çalıştırma izinlerini kontrol et
echo -e "${BLUE}[4/8] Script İzinleri Kontrolü${NC}"
for script in "${SCRIPTS[@]}"; do
    if [ -f "$PROJECT_DIR/$script" ]; then
        if [ -x "$PROJECT_DIR/$script" ]; then
            echo -e "${GREEN}✅ $script çalıştırılabilir${NC}"
        else
            echo -e "${RED}❌ $script çalıştırılabilir değil!${NC}"
            echo -e "${YELLOW}   Çözüm: chmod +x $PROJECT_DIR/$script${NC}"
        fi
    fi
done
echo ""

# 5. Script içeriklerini kontrol et (bash shebang, yol kontrolü)
echo -e "${BLUE}[5/8] Script İçerik Kontrolü${NC}"
for script in "${SCRIPTS[@]}"; do
    if [ -f "$PROJECT_DIR/$script" ]; then
        if head -1 "$PROJECT_DIR/$script" | grep -q "^#!/bin/bash"; then
            echo -e "${GREEN}✅ $script doğru shebang'e sahip${NC}"
        else
            echo -e "${YELLOW}⚠️  $script shebang kontrolü başarısız${NC}"
        fi
        
        # Yol kontrolü (batch_processor için özel kontrol)
        if grep -q "$PROJECT_DIR" "$PROJECT_DIR/$script" 2>/dev/null || grep -q "cd.*manav_analiz\|doluluk" "$PROJECT_DIR/$script" 2>/dev/null; then
            echo -e "${GREEN}✅ $script yol yapılandırması mevcut${NC}"
        else
            echo -e "${YELLOW}⚠️  $script yol yapılandırması eksik olabilir${NC}"
        fi
    fi
done
echo ""

# 6. Log dosyalarını kontrol et
echo -e "${BLUE}[6/8] Log Dosyaları Kontrolü${NC}"
LOG_DIR="$PROJECT_DIR/logs"
mkdir -p "$LOG_DIR"

LOG_FILES=("cron-snapshot.log" "cron-batch.log" "cron-ptz-analysis.log")
for log_file in "${LOG_FILES[@]}"; do
    if [ -f "$LOG_DIR/$log_file" ]; then
        SIZE=$(stat -f%z "$LOG_DIR/$log_file" 2>/dev/null || stat -c%s "$LOG_DIR/$log_file" 2>/dev/null || echo "0")
        if [ "$SIZE" -gt 0 ]; then
            LAST_MODIFIED=$(stat -f "%Sm" "$LOG_DIR/$log_file" 2>/dev/null || stat -c "%y" "$LOG_DIR/$log_file" 2>/dev/null | cut -d' ' -f1,2 | cut -d'.' -f1)
            echo -e "${GREEN}✅ $log_file mevcut (Boyut: ${SIZE} bytes, Son değişiklik: $LAST_MODIFIED)${NC}"
            
            # Son 5 satırı göster
            if [ "$SIZE" -gt 0 ]; then
                echo -e "${CYAN}   Son 3 satır:${NC}"
                tail -n 3 "$LOG_DIR/$log_file" | sed 's/^/   /' | head -3
            fi
        else
            echo -e "${YELLOW}⚠️  $log_file boş (henüz çalışmamış olabilir)${NC}"
        fi
    else
        echo -e "${YELLOW}⚠️  $log_file bulunamadı (henüz çalışmamış olabilir)${NC}"
    fi
done
echo ""

# 7. Sistem loglarını kontrol et (cron çalışma kayıtları)
echo -e "${BLUE}[7/8] Sistem Logları Kontrolü${NC}"
if [ -f "/var/log/syslog" ]; then
    CRON_LOGS=$(grep -i "cron" /var/log/syslog | tail -5 2>/dev/null || echo "")
    if [ ! -z "$CRON_LOGS" ]; then
        echo -e "${GREEN}✅ Sistem loglarında cron kayıtları bulundu${NC}"
        echo -e "${CYAN}   Son 3 cron kaydı:${NC}"
        echo "$CRON_LOGS" | tail -3 | sed 's/^/   /'
    else
        echo -e "${YELLOW}⚠️  Sistem loglarında cron kaydı bulunamadı${NC}"
    fi
elif [ -f "/var/log/cron" ]; then
    CRON_LOGS=$(tail -5 /var/log/cron 2>/dev/null || echo "")
    if [ ! -z "$CRON_LOGS" ]; then
        echo -e "${GREEN}✅ Cron log dosyasında kayıtlar bulundu${NC}"
        echo -e "${CYAN}   Son 3 kayıt:${NC}"
        echo "$CRON_LOGS" | tail -3 | sed 's/^/   /'
    else
        echo -e "${YELLOW}⚠️  Cron log dosyası boş${NC}"
    fi
else
    echo -e "${YELLOW}⚠️  Sistem log dosyalarına erişilemiyor (sudo gerekebilir)${NC}"
fi
echo ""

# 8. Manuel test önerisi
echo -e "${BLUE}[8/8] Manuel Test Önerileri${NC}"
echo -e "${CYAN}Manuel test komutları:${NC}"
echo ""
echo -e "${YELLOW}# 1. Script'leri manuel çalıştırın:${NC}"
for script in "${SCRIPTS[@]}"; do
    if [ -f "$PROJECT_DIR/$script" ]; then
        echo "   $PROJECT_DIR/$script"
    fi
done
echo ""
echo -e "${YELLOW}# 2. Cronjob'ları test etmek için (1 dakika sonra çalışacak):${NC}"
echo "   # Crontab'a ekleyin:"
echo "   * * * * * $PROJECT_DIR/run_camera_snapshot.sh >> $LOG_DIR/test-cron.log 2>&1"
echo "   # 1 dakika bekleyin, sonra kontrol edin:"
echo "   tail -f $LOG_DIR/test-cron.log"
echo ""
echo -e "${YELLOW}# 3. Cronjob'ları yeniden kurmak için:${NC}"
echo "   ./setup_cronjobs.sh"
echo ""

# Özet
echo -e "${BLUE}========================================${NC}"
echo -e "${BLUE}Özet ve Öneriler${NC}"
echo -e "${BLUE}========================================${NC}"
echo ""

# Sorun tespiti
ISSUES=0

if ! systemctl is-active --quiet cron 2>/dev/null && ! systemctl is-active --quiet crond 2>/dev/null; then
    echo -e "${RED}❌ Sorun: Cron servisi çalışmıyor${NC}"
    echo -e "   ${YELLOW}Çözüm: sudo systemctl start cron${NC}"
    ISSUES=$((ISSUES + 1))
fi

if [ ${#MISSING_SCRIPTS[@]} -gt 0 ]; then
    echo -e "${RED}❌ Sorun: Eksik script dosyaları${NC}"
    echo -e "   ${YELLOW}Çözüm: DEPLOYMENT.md'ye bakın${NC}"
    ISSUES=$((ISSUES + 1))
fi

CRON_COUNT=$(crontab -l 2>/dev/null | grep -c "Carrefoursa Kamera" || echo "0")
if [ "$CRON_COUNT" -eq 0 ]; then
    echo -e "${RED}❌ Sorun: Cronjob'lar kurulu değil${NC}"
    echo -e "   ${YELLOW}Çözüm: ./setup_cronjobs.sh çalıştırın${NC}"
    ISSUES=$((ISSUES + 1))
fi

if [ $ISSUES -eq 0 ]; then
    echo -e "${GREEN}✅ Tüm kontroller başarılı!${NC}"
    echo ""
    echo -e "${CYAN}Eğer cronjob'lar hala çalışmıyorsa:${NC}"
    echo "   1. Log dosyalarını kontrol edin: tail -f $LOG_DIR/cron-*.log"
    echo "   2. Sistem loglarını kontrol edin: sudo grep CRON /var/log/syslog | tail -20"
    echo "   3. Script'leri manuel çalıştırıp hata mesajlarını kontrol edin"
    echo "   4. Cronjob zamanlamasını kontrol edin: crontab -l"
else
    echo ""
    echo -e "${YELLOW}⚠️  $ISSUES sorun tespit edildi. Yukarıdaki çözümleri uygulayın.${NC}"
fi

echo ""

