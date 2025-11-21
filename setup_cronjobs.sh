#!/bin/bash
# Cronjob Setup Script
# Bu script, tüm .sh dosyaları için cronjob'ları otomatik olarak oluşturur

set -e

# Renkli çıktı için
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo -e "${BLUE}========================================${NC}"
echo -e "${BLUE}Cronjob Kurulum Script'i${NC}"
echo -e "${BLUE}========================================${NC}"
echo ""

# Proje dizinini bul (script'in bulunduğu dizin)
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
echo -e "${BLUE}Kurulacak Script'ler:${NC}"
echo ""

# Script dosyalarını kontrol et
SCRIPTS=()

if [ -f "$PROJECT_DIR/run_camera_snapshot.sh" ]; then
    SCRIPTS+=("run_camera_snapshot.sh")
    echo -e "${GREEN}✅ run_camera_snapshot.sh bulundu${NC}"
else
    echo -e "${RED}❌ run_camera_snapshot.sh bulunamadı${NC}"
fi

if [ -f "$PROJECT_DIR/run_batch_processor.sh" ]; then
    SCRIPTS+=("run_batch_processor.sh")
    echo -e "${GREEN}✅ run_batch_processor.sh bulundu${NC}"
else
    echo -e "${RED}❌ run_batch_processor.sh bulunamadı${NC}"
fi

if [ -f "$PROJECT_DIR/run_ptz_analysis.sh" ]; then
    SCRIPTS+=("run_ptz_analysis.sh")
    echo -e "${GREEN}✅ run_ptz_analysis.sh bulundu${NC}"
else
    echo -e "${RED}❌ run_ptz_analysis.sh bulunamadı${NC}"
fi

echo ""

if [ ${#SCRIPTS[@]} -eq 0 ]; then
    echo -e "${RED}❌ Hiç script bulunamadı! Lütfen önce script'leri oluşturun.${NC}"
    exit 1
fi

# Log dizinini oluştur
mkdir -p "$PROJECT_DIR/logs"

# Mevcut crontab'ı yedekle
BACKUP_FILE="$PROJECT_DIR/logs/crontab_backup_$(date +%Y%m%d_%H%M%S).txt"
crontab -l > "$BACKUP_FILE" 2>/dev/null || echo "# Crontab backup - $(date)" > "$BACKUP_FILE"
echo -e "${GREEN}✅ Mevcut crontab yedeklendi: $BACKUP_FILE${NC}"
echo ""

# Cronjob zamanlarını ayarla
echo -e "${BLUE}Cronjob Zamanları:${NC}"
echo ""
echo -e "${YELLOW}1. Camera Snapshot:${NC}"
echo "   Her saat başı (9:00 - 21:00 arası)"
echo "   Format: 0 9-21 * * *"
echo ""
echo -e "${YELLOW}2. Batch Processor:${NC}"
echo "   Her saat 35'de (9:35 - 21:35 arası)"
echo "   Format: 35 9-21 * * *"
echo ""
echo -e "${YELLOW}3. PTZ Analysis:${NC}"
echo "   Her saat 20'de (9:20 - 21:20 arası)"
echo "   Format: 20 9-21 * * *"
echo ""

# Kullanıcıdan onay al
read -p "Bu zamanlarda cronjob'ları kurmak istiyor musunuz? (E/h): " -n 1 -r
echo ""
if [[ ! $REPLY =~ ^[EeYy]$ ]]; then
    echo -e "${YELLOW}İşlem iptal edildi.${NC}"
    exit 0
fi

echo ""
echo -e "${BLUE}Cronjob'lar ekleniyor...${NC}"
echo ""

# Mevcut crontab'ı al
TEMP_CRON=$(mktemp)
crontab -l > "$TEMP_CRON" 2>/dev/null || echo "" > "$TEMP_CRON"

# Eski cronjob'ları temizle (aynı script'ler için)
sed -i '/run_camera_snapshot.sh/d' "$TEMP_CRON"
sed -i '/run_batch_processor.sh/d' "$TEMP_CRON"
sed -i '/run_ptz_analysis.sh/d' "$TEMP_CRON"

# Yeni cronjob'ları ekle
{
    echo ""
    echo "# ============================================"
    echo "# Carrefoursa Kamera Entegrasyon Cronjobs"
    echo "# Oluşturulma: $(date '+%Y-%m-%d %H:%M:%S')"
    echo "# ============================================"
    echo ""
    
    # Camera Snapshot - Her saat başı (9:00-21:00)
    if [[ " ${SCRIPTS[@]} " =~ " run_camera_snapshot.sh " ]]; then
        echo "# Camera Snapshot - Her saat başı (9:00-21:00)"
        echo "0 9-21 * * * $PROJECT_DIR/run_camera_snapshot.sh >> $PROJECT_DIR/logs/cron-snapshot.log 2>&1"
        echo ""
    fi
    
    # Batch Processor - Her saat 35'de (9:35-21:35)
    if [[ " ${SCRIPTS[@]} " =~ " run_batch_processor.sh " ]]; then
        echo "# Batch Processor - Her saat 35'de (9:35-21:35)"
        echo "35 9-21 * * * $PROJECT_DIR/run_batch_processor.sh >> $PROJECT_DIR/logs/cron-batch.log 2>&1"
        echo ""
    fi
    
    # PTZ Analysis - Her saat 20'de (9:20-21:20)
    if [[ " ${SCRIPTS[@]} " =~ " run_ptz_analysis.sh " ]]; then
        echo "# PTZ Analysis - Her saat 20'de (9:20-21:20)"
        echo "20 9-21 * * * $PROJECT_DIR/run_ptz_analysis.sh >> $PROJECT_DIR/logs/cron-ptz-analysis.log 2>&1"
        echo ""
    fi
    
} >> "$TEMP_CRON"

# Crontab'ı güncelle
crontab "$TEMP_CRON"
rm "$TEMP_CRON"

echo -e "${GREEN}✅ Cronjob'lar başarıyla eklendi!${NC}"
echo ""

# Mevcut crontab'ı göster
echo -e "${BLUE}Mevcut Crontab:${NC}"
echo ""
crontab -l | grep -A 20 "Carrefoursa Kamera"
echo ""

# Test için bilgi
echo -e "${BLUE}Test Komutları:${NC}"
echo ""
echo -e "${YELLOW}# Cronjob'ları listelemek için:${NC}"
echo "crontab -l"
echo ""
echo -e "${YELLOW}# Log dosyalarını izlemek için:${NC}"
if [[ " ${SCRIPTS[@]} " =~ " run_camera_snapshot.sh " ]]; then
    echo "tail -f $PROJECT_DIR/logs/cron-snapshot.log"
fi
if [[ " ${SCRIPTS[@]} " =~ " run_batch_processor.sh " ]]; then
    echo "tail -f $PROJECT_DIR/logs/cron-batch.log"
fi
if [[ " ${SCRIPTS[@]} " =~ " run_ptz_analysis.sh " ]]; then
    echo "tail -f $PROJECT_DIR/logs/cron-ptz-analysis.log"
fi
echo ""
echo -e "${YELLOW}# Cronjob'ları kaldırmak için:${NC}"
echo "crontab -e"
echo "# İlgili satırları silin veya başına # ekleyin"
echo ""
echo -e "${GREEN}✅ Kurulum tamamlandı!${NC}"
echo ""

