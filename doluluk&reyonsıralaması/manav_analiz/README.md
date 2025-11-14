# Manav Analiz FastAPI (Azure OpenAI)

Mağaza manav bölümündeki kameralardan gelen görüntülerde **Azure OpenAI GPT-4 Vision** kullanarak analiz yapan REST API sistemi.

## 📋 API Endpoint'leri

### 1. 🔍 POST `/analyze/content` - Reyon İçerik Analizi
### 2. 📊 POST `/analyze/stock` - Kritik Stok Analizi  
### 3. 🏥 GET `/health` - Sağlık kontrolü
### 4. 🤖 GET `/models` - Mevcut modeller
### 5. 🧪 POST `/test-model` - Model testi

## 🚀 Kurulum & Çalıştırma

```bash
# Bağımlılıkları yükle
pip install -r requirements.txt

# Azure OpenAI ayarlarını yap (.env dosyası oluştur)
AZURE_OPENAI_ENDPOINT=https://your-resource-name.openai.azure.com/
AZURE_OPENAI_API_KEY=your_azure_api_key_here
AZURE_OPENAI_DEPLOYMENT=gpt-4o  # veya gpt-4-turbo, gpt-4
AZURE_API_VERSION=2024-02-15-preview

# API'yi başlat
python main.py

# Model kontrolü: http://localhost:8000/models
# Model testi: http://localhost:8000/test-model
# API dokümantasyonu: http://localhost:8000/docs
```

## 🔍 Model Seçimi

Azure Portal'dan hangi modeli deploy ettiğini kontrol et:

1. **Azure Portal → OpenAI Resource → Model deployments**
2. **Mevcut deployment'ın adını .env'e yaz**

Yaygın model isimleri:
- `gpt-4o` (en yeni, vision destekli) ✅ 
- `gpt-4-turbo` (vision destekli) ✅
- `gpt-4` (vision destekli) ✅
- `gpt-35-turbo` (vision desteksiz) ❌

## 📡 API Kullanımı

### cURL ile test:
```bash
# İçerik analizi
curl -X POST "http://localhost:8000/analyze/content" \
     -H "accept: application/json" \
     -H "Content-Type: multipart/form-data" \
     -F "file=@manav_goruntusu.jpg"

# Stok analizi  
curl -X POST "http://localhost:8000/analyze/stock" \
     -H "accept: application/json" \
     -H "Content-Type: multipart/form-data" \
     -F "file=@manav_goruntusu.jpg"
```

### Python ile kullanım:
```python
import requests

# İçerik analizi
with open("manav.jpg", "rb") as f:
    files = {"file": ("manav.jpg", f, "image/jpeg")}
    response = requests.post("http://localhost:8000/analyze/content", files=files)
    result = response.json()

# Stok analizi
with open("manav.jpg", "rb") as f:
    files = {"file": ("manav.jpg", f, "image/jpeg")}
    response = requests.post("http://localhost:8000/analyze/stock", files=files)
    result = response.json()
```

## 📊 Yanıt Formatları

### İçerik Analizi Yanıtı:
```json
{
  "success": true,
  "data": {
    "reyonlar": [
      {
        "reyon_id": "ust_sol",
        "ana_urun": "elma",
        "yan_urunler": ["armut", "muz"],
        "konum_detay": "sol tarafta elma, sağ tarafta armut"
      }
    ],
    "urun_iliskileri": {
      "elma": ["armut", "muz"],
      "domates": ["salatalik", "biber"]
    }
  },
  "timestamp": "2025-10-21T..."
}
```

### Stok Analizi Yanıtı:
```json
{
  "success": true,
  "data": {
    "kritik_reyonlar": [
      {
        "reyon_id": "alt_orta",
        "doluluk": 0.2,
        "durum": "kritik_düşük",
        "aciliyet": "yüksek",
        "kasa_gorunurlugu": true
      }
    ],
    "doluluk_seviyeleri": {
      "boş": ["reyon_1"],
      "kritik": ["reyon_2", "reyon_3"],
      "normal": ["reyon_4"],
      "dolu": ["reyon_5"]
    }
  },
  "timestamp": "2025-10-21T..."
}
```

## 🧪 Test

```bash
# API testlerini çalıştır
python test_api.py
```

## 📁 Proje Yapısı

```
manav_analiz/
├── main.py              # FastAPI uygulaması
├── test_api.py          # API test scripti
├── requirements.txt     # Python bağımlılıkları
├── .env.example        # Örnek environment dosyası
└── README.md           # Bu dosya
```

## 🔧 Konfigürasyon

### Azure OpenAI Ayarları:
```bash
AZURE_OPENAI_ENDPOINT=https://your-resource-name.openai.azure.com/
AZURE_OPENAI_API_KEY=your_azure_api_key_here
AZURE_OPENAI_DEPLOYMENT=gpt-4-vision
AZURE_API_VERSION=2024-02-15-preview
```

### API Ayarları:
- **Port**: 8000
- **Host**: 0.0.0.0  
- **Model**: Azure GPT-4 Vision
- **Max Tokens**: 1500
- **Temperature**: 0.3

## � API Dokümantasyonu

API çalıştırıldıktan sonra otomatik dokümantasyon:
- **Swagger UI**: http://localhost:8000/docs
- **ReDoc**: http://localhost:8000/redoc

## 🎨 Avantajlar

✅ **Azure Integration**: Azure OpenAI Service ile güvenli ve scalable  
✅ **No Computer Vision**: YOLO, OpenCV gereksiz - sadece GPT-4 Vision  
✅ **REST API**: Standart HTTP endpoint'leri  
✅ **FastAPI**: Otomatik dokümantasyon, validasyon  
✅ **Minimal Dependencies**: Sadece gerekli paketler  
✅ **Enterprise Ready**: Azure altyapısı ile production hazır  

## 🔍 Sağlık Kontrolü

```bash
curl http://localhost:8000/health
```

## 📞 Destek

API sorunları için geliştirici ekibiyle iletişime geçin.