#!/bin/bash

# Carrefoursa Kamera Entegrasyon - Linux Kurulum Script'i
# Kullanım: sudo bash install.sh

set -e  # Hata durumunda dur

echo "=========================================="
echo "Carrefoursa Kamera Entegrasyon Kurulumu"
echo "=========================================="
echo ""

# Renkler
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Hata fonksiyonu
error_exit() {
    echo -e "${RED}HATA: $1${NC}" >&2
    exit 1
}

# Başarı mesajı
success_msg() {
    echo -e "${GREEN}✓ $1${NC}"
}

# Uyarı mesajı
warning_msg() {
    echo -e "${YELLOW}⚠ $1${NC}"
}

# 1. Sistem paketlerini kontrol et ve yükle
echo "1. Sistem paketleri kontrol ediliyor..."
if command -v apt-get &> /dev/null; then
    sudo apt-get update
    sudo apt-get install -y python3 python3-pip python3-venv git build-essential libpq-dev postgresql-client curl wget || error_exit "Sistem paketleri yüklenemedi"
elif command -v yum &> /dev/null; then
    sudo yum install -y python3 python3-pip python3-venv git gcc postgresql-devel curl wget || error_exit "Sistem paketleri yüklenemedi"
else
    error_exit "Desteklenmeyen paket yöneticisi (apt-get veya yum gerekli)"
fi
success_msg "Sistem paketleri yüklendi"

# 2. Python versiyonunu kontrol et
echo ""
echo "2. Python versiyonu kontrol ediliyor..."
PYTHON_VERSION=$(python3 --version 2>&1 | awk '{print $2}' | cut -d. -f1,2)
REQUIRED_VERSION="3.10"

if [ "$(printf '%s\n' "$REQUIRED_VERSION" "$PYTHON_VERSION" | sort -V | head -n1)" != "$REQUIRED_VERSION" ]; then
    error_exit "Python 3.10 veya üzeri gerekli. Mevcut versiyon: $PYTHON_VERSION"
fi
success_msg "Python versiyonu uygun: $PYTHON_VERSION"

# 3. Proje dizinini kontrol et
echo ""
echo "3. Proje dizini kontrol ediliyor..."
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
cd "$SCRIPT_DIR"

if [ ! -f "camera_snapshot_system.py" ] && [ ! -f "multi_camera_system/camera_snapshot_system.py" ]; then
    warning_msg "Proje dosyaları bulunamadı. Lütfen script'i proje dizininde çalıştırın."
fi
success_msg "Proje dizini: $SCRIPT_DIR"

# 4. Virtual environment oluştur
echo ""
echo "4. Python virtual environment oluşturuluyor..."
if [ -d "venv" ]; then
    warning_msg "Virtual environment zaten mevcut. Yeniden oluşturuluyor..."
    rm -rf venv
fi

python3 -m venv venv || error_exit "Virtual environment oluşturulamadı"
success_msg "Virtual environment oluşturuldu"

# 5. Virtual environment'ı aktif et ve pip'i güncelle
echo ""
echo "5. Pip güncelleniyor..."
source venv/bin/activate
pip install --upgrade pip setuptools wheel || error_exit "Pip güncellenemedi"
success_msg "Pip güncellendi"

# 6. Bağımlılıkları yükle
echo ""
echo "6. Python bağımlılıkları yükleniyor (bu işlem birkaç dakika sürebilir)..."
if [ -f "requirements.txt" ]; then
    pip install -r requirements.txt || error_exit "Bağımlılıklar yüklenemedi"
    success_msg "Bağımlılıklar requirements.txt'den yüklendi"
else
    warning_msg "requirements.txt bulunamadı, temel paketler yükleniyor..."
    pip install requests Pillow PyYAML numpy ultralytics torch torchvision \
        fastapi uvicorn python-multipart python-dotenv boto3 psycopg2-binary \
        azure-storage-blob facenet-pytorch openai || error_exit "Bağımlılıklar yüklenemedi"
    success_msg "Temel bağımlılıklar yüklendi"
fi

# 7. Gerekli dizinleri oluştur
echo ""
echo "7. Gerekli dizinler oluşturuluyor..."
mkdir -p snapshots crops logs
success_msg "Dizinler oluşturuldu"

# 8. .env dosyası kontrolü
echo ""
echo "8. .env dosyası kontrol ediliyor..."
if [ ! -f ".env" ]; then
    warning_msg ".env dosyası bulunamadı!"
    echo "Lütfen .env dosyasını oluşturun:"
    echo "  cp .env.example .env"
    echo "  nano .env"
else
    success_msg ".env dosyası mevcut"
fi

# 9. Model dosyalarını kontrol et
echo ""
echo "9. Model dosyaları kontrol ediliyor..."
if [ -f "best.pt" ]; then
    success_msg "best.pt bulundu"
else
    warning_msg "best.pt bulunamadı (YOLO otomatik indirecek)"
fi

if [ -f "yolov8s.pt" ]; then
    success_msg "yolov8s.pt bulundu"
else
    warning_msg "yolov8s.pt bulunamadı (YOLO otomatik indirecek)"
fi

# 10. İzinleri ayarla
echo ""
echo "10. Dosya izinleri ayarlanıyor..."
chmod +x multi_camera_system/camera_snapshot_system.py 2>/dev/null || true
chmod +x doluluk\&reyonsıralaması/manav_analiz/main.py 2>/dev/null || true
chmod +x doluluk\&reyonsıralaması/manav_analiz/batch_processor.py 2>/dev/null || true
success_msg "İzinler ayarlandı"

# 11. Systemd service dosyalarını oluştur (opsiyonel)
echo ""
echo "11. Systemd service dosyaları oluşturuluyor..."
read -p "Systemd service dosyalarını oluşturmak istiyor musunuz? (y/n): " -n 1 -r
echo
if [[ $REPLY =~ ^[Yy]$ ]]; then
    read -p "Servisleri çalıştıracak kullanıcı adını girin (varsayılan: $USER): " SERVICE_USER
    SERVICE_USER=${SERVICE_USER:-$USER}
    
    # Camera Snapshot Service
    sudo tee /etc/systemd/system/camera-snapshot.service > /dev/null <<EOF
[Unit]
Description=Carrefoursa Camera Snapshot System
After=network.target postgresql.service

[Service]
Type=simple
User=$SERVICE_USER
WorkingDirectory=$SCRIPT_DIR
Environment="PATH=$SCRIPT_DIR/venv/bin"
ExecStart=$SCRIPT_DIR/venv/bin/python $SCRIPT_DIR/multi_camera_system/camera_snapshot_system.py
Restart=always
RestartSec=10
StandardOutput=append:$SCRIPT_DIR/logs/camera-snapshot.log
StandardError=append:$SCRIPT_DIR/logs/camera-snapshot-error.log

[Install]
WantedBy=multi-user.target
EOF

    # Manav API Service
    sudo tee /etc/systemd/system/manav-api.service > /dev/null <<EOF
[Unit]
Description=Manav Analiz API Service
After=network.target

[Service]
Type=simple
User=$SERVICE_USER
WorkingDirectory=$SCRIPT_DIR/doluluk&reyonsıralaması/manav_analiz
Environment="PATH=$SCRIPT_DIR/venv/bin"
ExecStart=$SCRIPT_DIR/venv/bin/uvicorn main:app --host 0.0.0.0 --port 8000
Restart=always
RestartSec=10
StandardOutput=append:$SCRIPT_DIR/logs/manav-api.log
StandardError=append:$SCRIPT_DIR/logs/manav-api-error.log

[Install]
WantedBy=multi-user.target
EOF

    # Batch Processor Service
    sudo tee /etc/systemd/system/batch-processor.service > /dev/null <<EOF
[Unit]
Description=Batch Processor Service
After=network.target postgresql.service manav-api.service

[Service]
Type=simple
User=$SERVICE_USER
WorkingDirectory=$SCRIPT_DIR/doluluk&reyonsıralaması/manav_analiz
Environment="PATH=$SCRIPT_DIR/venv/bin"
ExecStart=$SCRIPT_DIR/venv/bin/python $SCRIPT_DIR/doluluk&reyonsıralaması/manav_analiz/batch_processor.py
Restart=always
RestartSec=30
StandardOutput=append:$SCRIPT_DIR/logs/batch-processor.log
StandardError=append:$SCRIPT_DIR/logs/batch-processor-error.log

[Install]
WantedBy=multi-user.target
EOF

    sudo systemctl daemon-reload
    success_msg "Systemd service dosyaları oluşturuldu"
    echo ""
    echo "Servisleri başlatmak için:"
    echo "  sudo systemctl enable camera-snapshot manav-api batch-processor"
    echo "  sudo systemctl start camera-snapshot manav-api batch-processor"
else
    warning_msg "Systemd service dosyaları oluşturulmadı"
fi

# Kurulum tamamlandı
echo ""
echo "=========================================="
echo -e "${GREEN}Kurulum tamamlandı!${NC}"
echo "=========================================="
echo ""
echo "Sonraki adımlar:"
echo "1. .env dosyasını oluşturun ve düzenleyin"
echo "2. Kamera konfigürasyon dosyalarını kontrol edin"
echo "3. Servisleri başlatın (eğer systemd kullanıyorsanız)"
echo ""
echo "Manuel çalıştırma:"
echo "  source venv/bin/activate"
echo "  python multi_camera_system/camera_snapshot_system.py"
echo "  cd doluluk&reyonsıralaması/manav_analiz && uvicorn main:app --host 0.0.0.0 --port 8000"
echo ""

