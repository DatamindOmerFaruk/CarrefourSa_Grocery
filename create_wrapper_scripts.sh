#!/bin/bash
# Wrapper Script'leri Oluşturma Script'i (Linux)
# Bu script, tüm wrapper script'lerini otomatik olarak oluşturur

set -e

# Renkli çıktı için
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo -e "${BLUE}========================================${NC}"
echo -e "${BLUE}Wrapper Script'leri Oluşturma${NC}"
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

# 1. Camera Snapshot Wrapper Script
echo -e "${BLUE}[1/3] Camera Snapshot Wrapper Script oluşturuluyor...${NC}"
cat > "$PROJECT_DIR/run_camera_snapshot.sh" << 'EOF'
#!/bin/bash
# Camera Snapshot Wrapper Script
# Bu script, camera_snapshot_system.py'yi çalıştırmak için kullanılır

# Hata durumunda dur
set -e

# Proje dizinine geç
cd /data/carrefoursa-kamera/CarrefourSa_Grocery

# Virtual environment'ı aktif et
source venv/bin/activate

# Log dizinini oluştur (yoksa)
mkdir -p logs

# Camera Snapshot System'i çalıştır
python multi_camera_system/camera_snapshot_system.py
EOF

chmod +x "$PROJECT_DIR/run_camera_snapshot.sh"
echo -e "${GREEN}✅ run_camera_snapshot.sh oluşturuldu${NC}"
echo ""

# 2. Batch Processor Wrapper Script
echo -e "${BLUE}[2/3] Batch Processor Wrapper Script oluşturuluyor...${NC}"
cat > "$PROJECT_DIR/run_batch_processor.sh" << 'EOF'
#!/bin/bash
# Batch Processor Wrapper Script
# Bu script, batch_processor.py'yi çalıştırmak için kullanılır

# Hata durumunda dur
set -e

# Proje dizinine geç (klasör adında & karakteri var, tırnak içine al)
cd "/data/carrefoursa-kamera/CarrefourSa_Grocery/doluluk&reyonsıralaması/manav_analiz"

# Virtual environment'ı aktif et
source ../../venv/bin/activate

# Log dizinini oluştur (yoksa)
mkdir -p ../../logs

# Batch processor'ı çalıştır (mod 2: Content + Stock + Evaluation)
# echo "2" komutu, batch_processor.py'nin interaktif mod seçimine "2" cevabını verir
echo "2" | python batch_processor.py
EOF

chmod +x "$PROJECT_DIR/run_batch_processor.sh"
echo -e "${GREEN}✅ run_batch_processor.sh oluşturuldu${NC}"
echo ""

# 3. PTZ Analysis Wrapper Script
echo -e "${BLUE}[3/3] PTZ Analysis Wrapper Script oluşturuluyor...${NC}"
cat > "$PROJECT_DIR/run_ptz_analysis.sh" << 'EOF'
#!/bin/bash
# PTZ Analysis Service Wrapper Script
# Bu script, PTZ analiz servislerini sırayla çalıştırır

# Hata durumunda dur
set -e

# Proje dizinine geç
cd /data/carrefoursa-kamera/CarrefourSa_Grocery

# Virtual environment'ı aktif et
source venv/bin/activate

# Log dizinini oluştur (yoksa)
mkdir -p logs

# ============================================
# AŞAMA 1: Yüz Blur'lanması
# ============================================
echo "[$(date '+%Y-%m-%d %H:%M:%S')] PTZ Face Blur başlatılıyor..."
echo "============================================"
python ptz_face_blur.py 2>&1 | tee -a logs/cron-ptz-face-blur.log
FACE_BLUR_EXIT_CODE=${PIPESTATUS[0]}
echo "============================================"

if [ $FACE_BLUR_EXIT_CODE -ne 0 ]; then
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] PTZ Face Blur hatası: $FACE_BLUR_EXIT_CODE"
    exit $FACE_BLUR_EXIT_CODE
fi

# ============================================
# AŞAMA 2: YOLO Detection ve LLM Analizi
# ============================================
echo "[$(date '+%Y-%m-%d %H:%M:%S')] PTZ YOLO + LLM Analysis başlatılıyor..."
echo "============================================"
python ptz_yolo_llm_analysis.py 2>&1 | tee -a logs/cron-ptz-yolo-llm.log
YOLO_EXIT_CODE=${PIPESTATUS[0]}
echo "============================================"

# YOLO analizi başarılı mı kontrol et
if [ $YOLO_EXIT_CODE -eq 0 ]; then
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] PTZ YOLO + LLM Analysis tamamlandı"
    
    # ============================================
    # AŞAMA 3: Veritabanına Yazma
    # ============================================
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] PTZ Database Writer başlatılıyor..."
    echo "============================================"
    python ptz_db_writer.py 2>&1 | tee -a logs/cron-ptz-db-writer.log
    DB_EXIT_CODE=${PIPESTATUS[0]}
    echo "============================================"
    
    # Veritabanı yazma başarılı mı kontrol et
    if [ $DB_EXIT_CODE -eq 0 ]; then
        echo "[$(date '+%Y-%m-%d %H:%M:%S')] PTZ Database Writer tamamlandı"
        echo "[$(date '+%Y-%m-%d %H:%M:%S')] Tüm PTZ analiz işlemleri başarıyla tamamlandı"
        exit 0
    else
        echo "[$(date '+%Y-%m-%d %H:%M:%S')] PTZ Database Writer hatası: $DB_EXIT_CODE"
        exit $DB_EXIT_CODE
    fi
else
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] PTZ YOLO + LLM Analysis hatası: $YOLO_EXIT_CODE"
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] Veritabanı yazma işlemi atlandı (YOLO analizi başarısız)"
    exit $YOLO_EXIT_CODE
fi
EOF

chmod +x "$PROJECT_DIR/run_ptz_analysis.sh"
echo -e "${GREEN}✅ run_ptz_analysis.sh oluşturuldu${NC}"
echo ""

# Özet
echo -e "${BLUE}========================================${NC}"
echo -e "${GREEN}✅ Tüm wrapper script'ler oluşturuldu!${NC}"
echo -e "${BLUE}========================================${NC}"
echo ""
echo -e "${CYAN}Oluşturulan Script'ler:${NC}"
ls -lh "$PROJECT_DIR/run_*.sh"
echo ""
echo -e "${YELLOW}Sonraki Adımlar:${NC}"
echo "1. Script'leri test edin: ./run_camera_snapshot.sh"
echo "2. Cronjob'ları kurun: ./setup_cronjobs.sh"
echo "3. Cronjob'ları kontrol edin: ./check_cronjobs.sh"
echo ""

