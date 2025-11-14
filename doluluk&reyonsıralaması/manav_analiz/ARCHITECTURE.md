# Manav Analiz Sistemi - Mimari Diagram

## Sistem Mimarisi

```mermaid
graph TB
    subgraph "Görüntü Kaynağı"
        CAM[Kamera Sistemi<br/>multi_camera_system]
        CAM -->|PTZ Snapshot| AZURE_STORAGE
    end
    
    subgraph "Azure Cloud"
        AZURE_STORAGE[Azure Blob Storage<br/>Container: snapshot<br/>📦 Görüntü Depolama]
        AZURE_OPENAI[Azure OpenAI<br/>GPT-4.1 Vision<br/>🤖 LLM Analiz Servisi]
    end
    
    subgraph "Batch İşleme Katmanı"
        BATCH[Batch Processor<br/>batch_processor.py<br/>⚙️ Toplu İşleme]
        BATCH -->|1. Liste Görseller| AZURE_STORAGE
        BATCH -->|2. SAS URL Al| AZURE_STORAGE
        BATCH -->|3. API Çağrıları| API_SERVICE
    end
    
    subgraph "API Servisi"
        API_SERVICE[FastAPI Service<br/>main.py:8000<br/>🌐 REST API]
        
        subgraph "API Endpoints"
            EP1[POST /analyze/content<br/>📋 İçerik Analizi]
            EP2[POST /analyze/stock<br/>📊 Stok Analizi]
            EP3[POST /analyze/evaluation<br/>🏥 Yerleşim Değerlendirme]
            EP4[POST /analyze/layout<br/>📐 Grid Düzeni]
        end
        
        API_SERVICE --> EP1
        API_SERVICE --> EP2
        API_SERVICE --> EP3
        API_SERVICE --> EP4
        
        subgraph "Görüntü İşleme"
            IMG_PROC[Image Processor<br/>PIL/Pillow<br/>✨ Kalite İyileştirme]
            IMG_PROC -->|Kontrast| IMG_PROC
            IMG_PROC -->|Netlik| IMG_PROC
            IMG_PROC -->|Renk Doygunluğu| IMG_PROC
            IMG_PROC -->|Base64 Encoding| AZURE_OPENAI
        end
        
        EP1 -->|Görüntü + Prompt| IMG_PROC
        EP2 -->|Görüntü + Prompt| IMG_PROC
        EP3 -->|Görüntü + Prompt| IMG_PROC
    end
    
    subgraph "AI Analiz"
        PROMPTS[Prompt Şablonları<br/>📝 CONTENT_PROMPT<br/>📝 STOCK_PROMPT<br/>📝 EVALUATION_PROMPT]
        PROMPTS --> AZURE_OPENAI
        AZURE_OPENAI -->|JSON Response| API_SERVICE
    end
    
    subgraph "Veritabanı Katmanı"
        POSTGRES[(PostgreSQL Database<br/>🗄️ Sonuç Depolama)]
        
        subgraph "Tablo Yapısı"
            TABLE1[analyze_row<br/>İçerik Analizi]
            TABLE2[analyze_stock_row<br/>Stok Durumu]
            TABLE3[analyze_evaluation_row<br/>Yerleşim Değerlendirme]
        end
        
        POSTGRES --> TABLE1
        POSTGRES --> TABLE2
        POSTGRES --> TABLE3
    end
    
    API_SERVICE -->|JSON Sonuç| BATCH
    BATCH -->|4. Sonuçları Kaydet| POSTGRES
    
    style CAM fill:#e1f5ff
    style AZURE_STORAGE fill:#0089d6,color:#fff
    style AZURE_OPENAI fill:#0078d4,color:#fff
    style BATCH fill:#ff9800,color:#fff
    style API_SERVICE fill:#00d977,color:#fff
    style POSTGRES fill:#336791,color:#fff
    style IMG_PROC fill:#ffeb3b
    style PROMPTS fill:#9c27b0,color:#fff
```

## Veri Akışı (Data Flow)

```mermaid
sequenceDiagram
    participant C as Kamera Sistemi
    participant AS as Azure Storage
    participant BP as Batch Processor
    participant API as FastAPI Service
    participant AI as Azure OpenAI GPT-4.1
    participant DB as PostgreSQL
    
    Note over C,AS: Görüntü Çekme
    C->>AS: PTZ Snapshot Upload (JPEG)
    
    Note over BP,AS: Batch İşleme Başlatma
    BP->>AS: List Blobs (Tüm görseller)
    AS-->>BP: Görsel Listesi + SAS URL
    
    loop Her Görsel İçin
        Note over BP,API: 1. İçerik Analizi
        BP->>API: POST /analyze/content<br/>(SAS URL)
        API->>API: Görüntü İyileştirme<br/>(PIL: Kontrast, Netlik)
        API->>AI: GPT-4.1 Vision API<br/>(CONTENT_PROMPT + Base64 Image)
        AI-->>API: JSON: Grid + Ürün Listesi
        API-->>BP: Analiz Sonucu
        
        Note over BP,API: 2. Stok Analizi
        BP->>API: POST /analyze/stock<br/>(SAS URL)
        API->>AI: GPT-4.1 Vision API<br/>(STOCK_PROMPT + Base64 Image)
        AI-->>API: JSON: Doluluk Durumları
        API-->>BP: Stok Analiz Sonucu
        
        Note over BP,API: 3. Yerleşim Değerlendirme
        BP->>API: POST /analyze/evaluation<br/>(SAS URL + Content Data)
        API->>AI: GPT-4.1 Vision API<br/>(EVALUATION_PROMPT + Image)
        AI-->>API: JSON: Hata Listesi + Öneriler
        API-->>BP: Değerlendirme Sonucu
        
        Note over BP,DB: Veritabanına Kaydetme
        BP->>DB: INSERT INTO analyze_row
        BP->>DB: INSERT INTO analyze_stock_row
        BP->>DB: INSERT INTO analyze_evaluation_row
    end
```

## Sistem Bileşenleri Detayı

### 1. Görüntü Kaynağı
- **Kamera Sistemi**: PTZ kameralardan snapshot alır
- **Format**: JPEG görüntüler
- **Hedef**: Azure Blob Storage'a yüklenir

### 2. Azure Blob Storage
- **Container**: `snapshot`
- **Fonksiyon**: Görüntü deposu
- **Erişim**: SAS Token ile güvenli erişim

### 3. Batch Processor
- **Dosya**: `batch_processor.py`
- **Modlar**:
  - **Mod 1**: Tam Analiz (Content + Stock + Evaluation)
  - **Mod 2**: Sadece Stock Analizi (Hızlı)
- **Özellikler**:
  - Batch işleme (default: 10 görsel/batch)
  - Retry mekanizması (3 deneme)
  - İlerleme takibi ve logging

### 4. FastAPI Service
- **Port**: 8000
- **Endpoints**:
  1. `/analyze/content` - Reyon içerik analizi
  2. `/analyze/stock` - Stok/doluluk analizi
  3. `/analyze/evaluation` - Yerleşim değerlendirmesi
  4. `/analyze/layout` - Grid düzeni tespiti

### 5. Görüntü İşleme Pipeline
```
Input Image → PIL Enhancement → Base64 Encoding → GPT-4.1 API
```
- **Kontrast Artırma**: %15
- **Netlik Artırma**: %10
- **Renk Doygunluğu**: %5
- **Çözünürlük**: Max 2560x1920 (Aspect ratio korunur)
- **Kalite**: JPEG 98% quality

### 6. Azure OpenAI GPT-4.1
- **Model**: GPT-4.1 Vision
- **API Version**: 2024-12-01-preview
- **Prompts**:
  - **CONTENT_PROMPT**: Meyve/sebze tanıma (detaylı)
  - **STOCK_PROMPT**: Stok seviyesi analizi (basit)
  - **EVALUATION_PROMPT**: Etilen kurallarına göre değerlendirme
- **Parameters**:
  - Max Tokens: 1500
  - Temperature: 0.2
  - Top-P: 0.9

### 7. PostgreSQL Veritabanı
- **Tablolar**:
  - `analyze_row`: İçerik analizi sonuçları (grid, ürünler, konumlar)
  - `analyze_stock_row`: Stok durumu (doluluk seviyeleri, özet)
  - `analyze_evaluation_row`: Yerleşim hataları ve öneriler

## Teknoloji Stack

### Backend
- **Python 3.x**
- **FastAPI** - REST API framework
- **Uvicorn** - ASGI server

### Cloud Services
- **Azure Blob Storage** - Görüntü depolama
- **Azure OpenAI** - GPT-4.1 Vision modeli

### Database
- **PostgreSQL** - İlişkisel veritabanı
- **Psycopg2** - PostgreSQL adapter

### Image Processing
- **Pillow (PIL)** - Görüntü işleme ve iyileştirme

### Utilities
- **Python-dotenv** - Environment variables
- **Requests** - HTTP client
- **Logging** - Sistem logları

## Güvenlik ve Konfigürasyon

### Environment Variables (.env)
```bash
# Azure Storage
AZURE_STORAGE_CONNECTION_STRING=...
AZURE_CONTAINER_NAME=snapshot
AZURE_SAS_TOKEN=...

# Azure OpenAI
AZURE_OPENAI_ENDPOINT=https://...
AZURE_OPENAI_API_KEY=...
AZURE_OPENAI_DEPLOYMENT=gpt-4.1
AZURE_API_VERSION=2024-12-01-preview

# PostgreSQL
POSTGRES_HOST=localhost
POSTGRES_PORT=5432
POSTGRES_DB=...
POSTGRES_USER=...
POSTGRES_PASSWORD=...

# API Configuration
API_BASE_URL=http://localhost:8000
BATCH_SIZE=10
RETRY_COUNT=3
REQUEST_DELAY=1.0
```

## Performans Özellikleri

- **Batch İşleme**: Toplu görsel işleme
- **Retry Mekanizması**: Başarısız istekler için 3 deneme
- **Request Throttling**: İstekler arası gecikme (default: 1s)
- **Progress Tracking**: İlerleme takibi ve loglama
- **Error Handling**: Kapsamlı hata yönetimi

## Kullanım Senaryoları

### Senaryo 1: Tam Analiz
```
Batch Processor → Content API → Stock API → Evaluation API → PostgreSQL
```

### Senaryo 2: Hızlı Stock Kontrolü
```
Batch Processor → Stock API → PostgreSQL
```

### Senaryo 3: Manuel API Çağrısı
```
Client → FastAPI → Azure OpenAI → JSON Response
```

