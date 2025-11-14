from fastapi import FastAPI, File, UploadFile, HTTPException, Form
from fastapi.responses import JSONResponse
from pydantic import BaseModel
import base64
import json
import os
from typing import Dict, Any, Optional
from PIL import Image
import io
from dotenv import load_dotenv
import requests

load_dotenv()

app = FastAPI(
    title="Manav Analiz API",
    description="Mağaza manav bölümü görüntü analizi API'leri (Azure OpenAI GPT-4.1)",
    version="1.0.0"
)

# Azure OpenAI konfigürasyonu (GPT-4.1)
AZURE_OPENAI_ENDPOINT = os.getenv('AZURE_OPENAI_ENDPOINT')
AZURE_OPENAI_API_KEY = os.getenv('AZURE_OPENAI_API_KEY')
AZURE_OPENAI_DEPLOYMENT = os.getenv('AZURE_OPENAI_DEPLOYMENT', 'gpt-4.1')  # GPT-4.1 deployment name
AZURE_API_VERSION = os.getenv('AZURE_API_VERSION', '2024-12-01-preview')

if not AZURE_OPENAI_ENDPOINT or not AZURE_OPENAI_API_KEY:
    raise ValueError("Azure OpenAI konfigürasyonu gerekli: AZURE_OPENAI_ENDPOINT ve AZURE_OPENAI_API_KEY")

# Prompt şablonları - GPT-4.1 için optimize edilmiş ve geliştirilmiş
CONTENT_PROMPT = """
Bu mağaza manav bölümü görüntüsünü detaylı analiz ederek meyve/sebze türlerini YÜKSEK DOĞRULUKLA tespit et!

🎯 GÖREV: Manav reyonlarını grid formatında analiz et ve meyve/sebzeleri kesin tanımla

1. Her reyonda hangi meyve/sebzeler var - DİKKATLİCE İNCELE
2. Aynı raf/kasa/bölümde birlikte duran ürünleri tespit et
3.Greyfurt meyvesini kullanma portakal var greyfurt yok.




📋 ANALİZ SÜRECİ:
1. Önce görüntüyü genel olarak incele ve kasa/reyon düzenini anla
2. Her kasayı ayrı ayrı zoom yaparak detaylı gözlemle
3. Meyve/sebzelerin karakteristik özelliklerini belirle (renk, şekil, doku, boyut)
4. Türkiye'deki yaygın manav ürünlerini önceliğe al
5- Görüntüyü çok dikkatli incele, küçük detayları da gör


🔍
🎯 GRİD ANALİZ YÖNTEMİ:
Görüntüdeki kasa düzenini belirle ve aşağıdaki formatlardan birini kullan:

KÜÇÜK DÜZENİ (2x4): 8 kasa
ORTA DÜZENİ (2x5): 10 kasa  
BÜYÜK DÜZENİ (3x4): 12 kasa
ÇOK BÜYÜK DÜZENİ (3x5): 15 kasa

Kesinlikle bu JSON formatında cevap ver:
{
    "grid_bilgisi": {
        "satir_sayisi": 2,
        "sutun_sayisi": 5,
        "toplam_kasa": 10
    },
    "tablo_format": {
        "baslik": ["Konum", "Ana Ürün", "Yan Ürünler"],
        "satirlar": [
            {
                "konum": "Üst Sol (1,1)",
                "ana_urun": "Domates",
                "yan_urunler": "Yok"
            }
        ]
    }
}

🔍 DETAYLI TANINMA KRİTERLERİ:

MEYVELER:
- Portakal: ORTA BOY, parlak turuncu renk, yuvarlak, pürüzsüz kabuk (greyfurttan KÜÇÜK)
- Elma: Kırmızı/yeşil/sarı, yuvarlak, pürüzsüz kabuk, üstte çukur
- Muz: Sarı/yeşil, uzun eğimli form, belirgin şeritler
- Armut: Açık yeşil/sarı, armut şekli (üst dar-alt geniş), pürüzsüz kabuk, uzun sap bölgesi
- Ayva: Altın sarısı renk, yuvarlağa yakın şekil, kabuk hafif pürüzlü, mat görünüm
- Limon: KÜÇÜK boy, oval, parlak sarı, sivri uçlar (portakaldan çok küçük)
- Nar: Kırmızı/pembe, yuvarlak, sert görünüm, üstte taç şekli
- Üzüm: Salkım halinde küçük taneler, mor/yeşil renk
- Kivi: Kahverengi tüylü kabuk, oval, orta boy
- Avokado: Koyu yeşil/siyah, oval/armut şekli, büyük boy

KÜÇÜK MEYVELER (BERRIES):
- Yaban Mersini: Çok küçük yuvarlak, koyu mavi/mor, matt görünüm, plastik kutuda
- Ahududu: Küçük konik, kırmızı, pürüzlü yüzey (tanecikli), plastik kutuda
- Böğürtlen: Ahudududan büyük, siyah/koyu mor, parlak pürüzlü yüzey
- Çilek: Konik şekil, kırmızı, üstte yeşil yaprakçık, yüzeyde sarı tohumlar
- Frenk Üzümü: Küçük yuvarlak, yeşil/sarı/kırmızı, şeffaf görünüm

SEBZELER:
- Domates: Kırmızı, yuvarlak, parlak
- Biber: Yeşil/kırmızı/sarı, uzun/kalın
- Patlıcan: Mor, uzun, parlak
- Kabak: Yeşil, uzun/yuvarlak
- Salatalık: Koyu yeşil, uzun, silindirik
- Marul: Açık yeşil, yapraklı, gevşek
- Ispanak: Koyu yeşil yapraklar
- Maydanoz: İnce yeşil yapraklar
- Soğan: Sarı/beyaz/mor, yuvarlak, kabuklu
- Patates: Kahverengi/sarı, oval, toprak izli

YEŞİLLİKLER:
- Roka: Küçük, çentikli yapraklar
- Nane: Küçük yeşil yapraklar
- Dereotu: İnce, tüylü yapraklar

🎯 TANıNMA KURALLARI:
- Her kasayı DİKKATLİCE incele - renk, şekil, boyut, doku
- BOYUT FARKI ÖNEMLİ: Greyfurt >> Portakal >> Limon sıralaması
- ŞEKIL FARKI: Armut (üst dar), Ayva (yuvarlak), Greyfurt (büyük yuvarlak)
- KÜÇÜK MEYVELER: Plastik kutularda olabilir, dikkatli bak
- Belirsiz durumda en olası ürünü söyle
- Konum: "Üst Sol (1,1)", "Üst Orta-Sol (1,2)" formatında
- Türkiye manav ürünlerini önceliğe al
- Boş kasalar için: "Boş" yaz

🚀 HEDEF: Maximum doğruluk ve güvenilir tanımlar!
"""

STOCK_PROMPT = """
Bu manav görüntüsünü incele ve her reyon/kasa için BASİT STOK DURUMU belirle!

🎯 GÖREV: Her kasa için praktik durum tespiti

📋 BASIT DEĞERLENDİRME:
1. Her kasayı tek tek bak
2. Hangi meyve/sebze var?
3. Ne kadar dolu? (Basit seviyeler)

🔍 DOLULUK SEVİYELERİ:
- **BOŞ**: Hiç ürün yok, kasa tamamen boş
- **Stok az**: Çok az ürün var, stok bitmek üzere  
- **NORMAL**: Yeterli stok var, orta seviye dolu
- **DOLU**: Kasa ağzına kadar dolu, bol stok

Kesinlikle bu JSON formatında cevap ver:
{
    "reyon_durumları": [
        {
            "konum": "Üst Sol (1,1)",
            "ürün": "Domates", 
            "durum": "dolu",
            "açıklama": "Domates kasası tamamen dolu"
        },
        {
            "konum": "Üst Orta (1,2)",
            "ürün": "Boş", 
            "durum": "boş",
            "açıklama": "Kasa tamamen boş"
        }
    ],
    "özet": {
        "toplam_kasa": 10,
        "boş_kasa": 1,
        "kritik_kasa": 2, 
        "normal_kasa": 4,
        "dolu_kasa": 3
    }
}

🚨 DİKKAT: 
- Kasa tabanı gözükse bile ürün varsa BOŞ değil!
- Basit ve anlaşılır açıklamalar yap
- Her kasa için durum belirle"""

EVALUATION_PROMPT = """
Bu manav düzenini değerlendir ve MANAV YERLEŞİM KURALLARINA göre analiz et!

🎯 GÖREV: Meyve/sebze yerleşimindeki HATALARI ve İYİLEŞTİRME ÖNERİLERİNİ tespit et

📋 MANAV YERLEŞİM KURALLARI - ETİLEN BAZLI SİSTEM:

ETİLEN KURALLARI VE ÜRÜN LİSTELERİ:

🔴 LİSTE 1: ETİLEN ÜRETİCİLERİ (Yüksek Etilen Salgılar)
Bu ürünler, Liste 2'deki ürünlerin hızla bozulmasına, sararmasına veya filizlenmesine neden olur.
Liste: Kayısı, Elma, Avokado, Trabzon hurması, Nektarin, Şeftali, Armutlar, Erik, Üzüm, Kabak, Domates, Kavun, Olgun muz, İncir, Soğan

🟡 LİSTE 2: ETİLENE HASSAS OLANLAR (Etilenden Çabuk Etkilenir)
Bu ürünler, Liste 1'deki ürünlerin yanına konulursa hızla bozulur.
Liste: Kuşkonmaz, Brokoli, Lahana, Biber, Havuç, Karnabahar, Kereviz, Salatalıklar, Taze fasulye, Pırasa, Bamya, Marul, Bezelye, Ispanak, Patates, Olgunlaşmamış muz, Kivi

🟢 LİSTE 3: NÖTRLER (Düşük Üretici / Düşük Hassasiyet)
Bu ürünler diğer ürünleri pek etkilemez ve diğerlerinden pek etkilenmezler. Her iki liste ile de yan yana durabilirler.
Liste: Yaban mersini, Kırmızıbiber, Kiraz, Mısır, Patlıcan, Çilek, Greyfurt, Portakal, Ananas, Karpuz, Ahududu, Sarımsak, Mantar, Böğürtlen

TEMEL SAKLAMA KURALLARI:
1. ❌ YASAK KOMBİNASYON: Liste 1'deki (Üreticiler) bir ürün, Liste 2'deki (Hassaslar) bir ürünle ASLA yan yana durmamalıdır. (Neden: Liste 1, Liste 2'yi bozar.)
2. ❌ ÖZEL YASAK KOMBİNASYON: Patates (Liste 2) ve Soğan (Liste 1) ASLA yan yana durmamalıdır. (Neden: Birbirlerinin filizlenmesini ve çürümesini hızlandırırlar.)
3. ✅ UYUMLU KOMBİNASYON (NÖTRLER): Liste 3'teki (Nötrler) ürünler, Liste 1, 2 veya 3'teki tüm ürünlerle yan yana durabilir.
4. ✅ UYUMLU KOMBİNASYON (HASSASLAR): Liste 2'deki (Hassaslar) ürünler kendi aralarında yan yana durabilir (Örn: Brokoli ve Lahana).

🔍 DEĞERLENDİRME KRİTERLERİ:
- Etilen gazı etkileşimleri
- Koku transferi riskleri
- Nem ve sıcaklık gereksinimleri
- Görsel uyum ve müşteri alışkanlıkları
- Hijyen ve çapraz bulaşma riskleri

Kesinlikle bu JSON formatında cevap ver:
{
    "degerlendirme_sonucu": {
        "genel_skor": 8.5,
        "toplam_hata": 3,
        "kritik_hata": 1,
        "uyari": 2
    },
    "tespit_edilen_hatalar": [
        {
            "hata_tipi": "kritik/uyari",
            "konum1": "Üst Sol (1,1)",
            "urun1": "Muz",
            "konum2": "Üst Orta-Sol (1,2)", 
            "urun2": "Marul",
            "problem": "Etilen üreten muz, yeşillikleri soldurur",
            "oneri": "Muz ile yeşillikler arasına en az 2 kasa mesafe bırakın"
        }
    ],
    "olumlu_yerlesimler": [
        {
            "konum1": "Alt Sol (2,1)",
            "urun1": "Portakal",
            "konum2": "Alt Orta-Sol (2,2)",
            "urun2": "Limon", 
            "sebep": "Turunçgiller yan yana ideal"
        }
    ],
    "genel_oneriler": [
        "Etilen üreten meyveleri ayrı bölüme yerleştirin",
        "Yeşillikleri soğuk ve nemli alanda tutun"
    ]
}

🚨 ÖNEMLİ: Gerçek manav bilgisi kullan, müşteri deneyimini düşün!
"""

# Response modelleri
class AnalysisResponse(BaseModel):
    success: bool
    data: Dict[str, Any] = None
    error: str = None
    timestamp: str


def encode_image_to_base64(image_bytes: bytes, enhance_quality: bool = True) -> str:
    """Görüntü bytes'ını base64'e çevirir - YÜKSEK KALİTE ve İyileştirmeli"""
    from PIL import ImageEnhance, ImageFilter
    
    image = Image.open(io.BytesIO(image_bytes))
    
    # Görüntü iyileştirme işlemleri
    if enhance_quality:
        # 1. Renk modunu RGB'ye çevir
        if image.mode != 'RGB':
            image = image.convert('RGB')
        
        # 2. Kontrast artırma (meyvelerin renklerini belirginleştir)
        enhancer = ImageEnhance.Contrast(image)
        image = enhancer.enhance(1.15)  # %15 kontrast artışı
        
        # 3. Netlik artırma (kenar detayları için)
        enhancer = ImageEnhance.Sharpness(image)
        image = enhancer.enhance(1.1)   # %10 netlik artışı
        
        # 4. Renk doygunluğunu hafif artır (meyve renklerini vurgulamak için)
        enhancer = ImageEnhance.Color(image)
        image = enhancer.enhance(1.05)  # %5 renk doygunluğu artışı
        
        # 5. Hafif gürültü azaltma filtresi
        image = image.filter(ImageFilter.SMOOTH_MORE)
    
    # Yüksek çözünürlük boyutu (GPT-4.1 maksimum limitine yakın)
    max_size = (2560, 1920)  # 4K benzeri çözünürlük
    
    # Aspect ratio'yu koru
    image.thumbnail(max_size, Image.Resampling.LANCZOS)
    
    # En yüksek kalite JPEG
    buffer = io.BytesIO()
    image.save(buffer, format='JPEG', quality=98, optimize=True, progressive=True)
    
    return base64.b64encode(buffer.getvalue()).decode('utf-8')


def download_image_from_url(image_url: str) -> bytes:
    """URL'den görüntü indir"""
    try:
        response = requests.get(image_url, timeout=30)
        response.raise_for_status()
        return response.content
    except Exception as e:
        raise Exception(f"Görüntü indirilemedi: {str(e)}")


def analyze_image_layout(image_bytes: bytes) -> Dict[str, Any]:
    """Görüntüdeki kasa düzenini analiz eder ve optimal grid boyutunu belirler"""
    
    # Görüntü bilgilerini al
    image = Image.open(io.BytesIO(image_bytes))
    width, height = image.size
    aspect_ratio = width / height
    
    # Görüntü boyutuna göre grid tahmini
    grid_configs = {
        "küçük": {"rows": 2, "cols": 3, "min_width": 800, "max_aspect": 1.3},
        "orta": {"rows": 2, "cols": 4, "min_width": 1000, "max_aspect": 1.6},
        "büyük": {"rows": 2, "cols": 5, "min_width": 1200, "max_aspect": 2.0},
        "çok_büyük": {"rows": 3, "cols": 5, "min_width": 1400, "max_aspect": 2.2},
        "mega": {"rows": 3, "cols": 6, "min_width": 1600, "max_aspect": 2.5}
    }
    
    # En uygun grid konfigürasyonunu seç
    selected_config = "orta"  # default
    
    for config_name, config in grid_configs.items():
        if width >= config["min_width"] and aspect_ratio <= config["max_aspect"]:
            selected_config = config_name
            break
    
    config = grid_configs[selected_config]
    
    return {
        "layout_type": selected_config,
        "rows": config["rows"],
        "cols": config["cols"],
        "total_boxes": config["rows"] * config["cols"],
        "image_width": width,
        "image_height": height,
        "aspect_ratio": round(aspect_ratio, 2)
    }


def generate_position_matrix(rows: int, cols: int) -> list:
    """Dinamik konum matrisi oluşturur"""
    
    positions = []
    
    # Satır adları
    row_names = ["Üst", "Orta", "Alt"] if rows == 3 else ["Üst", "Alt"]
    if rows > 3:
        row_names = [f"Satır-{i+1}" for i in range(rows)]
    
    # Sütun adları
    if cols == 3:
        col_names = ["Sol", "Orta", "Sağ"]
    elif cols == 4:
        col_names = ["Sol", "Orta-Sol", "Orta-Sağ", "Sağ"]
    elif cols == 5:
        col_names = ["Sol", "Orta-Sol", "Orta", "Orta-Sağ", "Sağ"]
    elif cols == 6:
        col_names = ["Sol", "Sol-Orta", "Orta-Sol", "Orta-Sağ", "Sağ-Orta", "Sağ"]
    else:
        col_names = [f"Sütun-{i+1}" for i in range(cols)]
    
    # Pozisyon isimlerini oluştur
    for i in range(rows):
        for j in range(cols):
            position_name = f"{row_names[i]} {col_names[j]} ({i+1},{j+1})"
            positions.append({
                "konum": position_name,
                "satir": i + 1,
                "sutun": j + 1,
                "ana_urun": "",
                "yan_urunler": "Yok"
            })
    
    return positions


def call_azure_openai_api(image_base64: str, prompt: str) -> str:
    """Azure OpenAI GPT-4.1 API çağrısı"""
    
    url = f"{AZURE_OPENAI_ENDPOINT}/openai/deployments/{AZURE_OPENAI_DEPLOYMENT}/chat/completions?api-version={AZURE_API_VERSION}"
    
    headers = {
        "Content-Type": "application/json",
        "api-key": AZURE_OPENAI_API_KEY
    }
    
    payload = {
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {
                        "type": "image_url",
                        "image_url": {"url": f"data:image/jpeg;base64,{image_base64}"}
                    }
                ]
            }
        ],
        "max_tokens": 1500,  # Sadece tablo için kısa yanıt
        "temperature": 0.2,  
        "top_p": 0.9,  
        "frequency_penalty": 0.0,
        "presence_penalty": 0.1
    }
    
    response = requests.post(url, headers=headers, json=payload, timeout=90)
    
    if response.status_code == 200:
        result = response.json()
        return result['choices'][0]['message']['content']
    else:
        raise Exception(f"Azure OpenAI API Error: {response.status_code} - {response.text}")


def parse_json_response(response: str) -> Dict:
    """LLM yanıtından JSON parse eder"""
    try:
        if '```json' in response:
            json_start = response.find('```json') + 7
            json_end = response.find('```', json_start)
            json_text = response[json_start:json_end].strip()
        elif '{' in response:
            json_start = response.find('{')
            json_end = response.rfind('}') + 1
            json_text = response[json_start:json_end]
        else:
            raise ValueError("JSON formatı bulunamadı")
        
        return json.loads(json_text)
    except json.JSONDecodeError as e:
        raise ValueError(f"JSON parse hatası: {str(e)}")


@app.get("/")
async def root():
    """API bilgi endpoint'i"""
    return {
        "message": "Manav Analiz API",
        "version": "1.0.0",
        "model": "Azure OpenAI GPT-4.1",
        "endpoints": {
            "POST /analyze/content": "Reyon içerik analizi",
            "POST /analyze/stock": "Kritik stok analizi",
            "POST /analyze/evaluation": "Yerleşim değerlendirmesi",
            "POST /analyze/layout": "Grid düzeni analizi",
            "GET /health": "Sağlık kontrolü"
        }
    }


@app.get("/health")
async def health_check():
    """Sağlık kontrolü"""
    return {
        "status": "healthy",
        "azure_openai_configured": bool(AZURE_OPENAI_ENDPOINT and AZURE_OPENAI_API_KEY),
        "deployment": AZURE_OPENAI_DEPLOYMENT,
        "api_version": AZURE_API_VERSION,
        "model": "GPT-4.1",
        "features": {
            "dynamic_grid_detection": True,
            "enhanced_image_processing": True,
            "high_accuracy_fruit_detection": True,
            "confidence_scoring": True
        }
    }


@app.post("/analyze/layout")
async def analyze_layout_only(file: UploadFile = File(...)):
    """
    📏 Sadece görüntü düzeni analizi - Grid boyutunu tespit et
    """
    try:
        if not file.content_type.startswith('image/'):
            raise HTTPException(status_code=400, detail="Sadece görüntü dosyaları kabul edilir")
        
        image_bytes = await file.read()
        layout_info = analyze_image_layout(image_bytes)
        position_matrix = generate_position_matrix(layout_info["rows"], layout_info["cols"])
        
        return {
            "success": True,
            "layout_info": layout_info,
            "position_count": len(position_matrix),
            "positions": [pos["konum"] for pos in position_matrix]
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/analyze/content", response_model=AnalysisResponse)
async def analyze_content(
    file: Optional[UploadFile] = File(None),
    image_url: Optional[str] = Form(None)
):
    """
    🔍 API 1: Reyon İçerik Analizi - Dinamik Grid Sistemi ile
    
    GPT-4.1 ile otomatik grid boyutu tespiti ve yüksek doğrulukla meyve/sebze tanıma
    İki mod: file upload veya image_url
    """
    try:
        # Girdi validasyonu
        if not file and not image_url:
            raise HTTPException(status_code=400, detail="File veya image_url gerekli")
        
        if file and image_url:
            raise HTTPException(status_code=400, detail="File ve image_url birlikte kullanılamaz")
        
        # Görüntüyü al
        if file:
            # Dosya validasyonu
            if not file.content_type.startswith('image/'):
                raise HTTPException(status_code=400, detail="Sadece görüntü dosyaları kabul edilir")
            image_bytes = await file.read()
        else:
            # URL'den indir
            image_bytes = download_image_from_url(image_url)
        
        # 1. Görüntü düzenini analiz et
        layout_info = analyze_image_layout(image_bytes)
        
        # 2. Dinamik pozisyon matrisi oluştur
        position_matrix = generate_position_matrix(layout_info["rows"], layout_info["cols"])
        
        # 3. Gelişmiş prompt oluştur (layout bilgisi ile)
        enhanced_prompt = f"""
{CONTENT_PROMPT}

📊 GÖRÜNTÜ DÜZENİ BİLGİSİ:
- Tespit edilen düzen: {layout_info['layout_type'].upper()}
- Satır sayısı: {layout_info['rows']}
- Sütun sayısı: {layout_info['cols']}
- Toplam kasa: {layout_info['total_boxes']}
- Görüntü boyutu: {layout_info['image_width']}x{layout_info['image_height']}
- Aspect ratio: {layout_info['aspect_ratio']}

🎯 BU DÜZENİ KULLAN:
{json.dumps([pos["konum"] for pos in position_matrix], ensure_ascii=False, indent=2)}

DİKKAT: Yukarıdaki konum listesine göre analiz yap!
        """
        
        # 4. Base64'e çevir (maksimum kalite ve iyileştirmeli)
        image_base64 = encode_image_to_base64(image_bytes, enhance_quality=True)
        
        # 5. Azure OpenAI GPT-4.1 API çağrısı
        response = call_azure_openai_api(image_base64, enhanced_prompt)
        
        # 6. JSON parse et
        result_data = parse_json_response(response)
        
        # Başarılı sonuç
        from datetime import datetime
        return AnalysisResponse(
            success=True,
            data=result_data,
            timestamp=datetime.now().isoformat()
        )
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/analyze/stock", response_model=AnalysisResponse)
async def analyze_stock(
    file: Optional[UploadFile] = File(None),
    image_url: Optional[str] = Form(None)
):
    """
    📊 API 2: Kritik Stok Analizi
    
    GPT-4.1 ile boş reyonlar ve kritik seviyeler
    """
    try:
        # Girdi validasyonu
        if not file and not image_url:
            raise HTTPException(status_code=400, detail="File veya image_url gerekli")
        
        if file and image_url:
            raise HTTPException(status_code=400, detail="File ve image_url birlikte kullanılamaz")
        
        # Görüntüyü al
        if file:
            # Dosya validasyonu
            if not file.content_type.startswith('image/'):
                raise HTTPException(status_code=400, detail="Sadece görüntü dosyaları kabul edilir")
            image_bytes = await file.read()
        else:
            # URL'den indir
            image_bytes = download_image_from_url(image_url)
        
        # Base64'e çevir (yüksek kalite)
        image_base64 = encode_image_to_base64(image_bytes, enhance_quality=True)
        
        # Azure OpenAI GPT-4.1 API çağrısı
        response = call_azure_openai_api(image_base64, STOCK_PROMPT)
        
        # JSON parse et
        result_data = parse_json_response(response)
        
        # Başarılı sonuç
        from datetime import datetime
        return AnalysisResponse(
            success=True,
            data=result_data,
            timestamp=datetime.now().isoformat()
        )
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/analyze/evaluation", response_model=AnalysisResponse)
async def analyze_evaluation(
    file: Optional[UploadFile] = File(None),
    image_url: Optional[str] = Form(None),
    content_data: Optional[str] = Form(None)
):
    """
    📊 API 3: Manav Yerleşim Değerlendirmesi
    
    İki mod destekler:
    1. Sadece görüntü → Otomatik analiz + değerlendirme
    2. Görüntü + content_data → 1. API sonucunu kullanarak değerlendirme (önerilen)
    """
    try:
        # Girdi validasyonu
        if not file and not image_url:
            raise HTTPException(status_code=400, detail="File veya image_url gerekli")
        
        if file and image_url:
            raise HTTPException(status_code=400, detail="File ve image_url birlikte kullanılamaz")
        
        # Görüntüyü al
        if file:
            # Dosya validasyonu
            if not file.content_type.startswith('image/'):
                raise HTTPException(status_code=400, detail="Sadece görüntü dosyaları kabul edilir")
            image_bytes = await file.read()
        else:
            # URL'den indir
            image_bytes = download_image_from_url(image_url)
        
        # content_data varsa kullan, yoksa görüntüden analiz et
        if content_data:
            try:
                # JSON string'i parse et
                content_result = json.loads(content_data)
                
                # 1. API sonucunu kullanarak değerlendirme yap
                enhanced_evaluation_prompt = f"""
{EVALUATION_PROMPT}

📋 MEVCUT DÜZEN BİLGİSİ (1. API'den):
{json.dumps(content_result, ensure_ascii=False, indent=2)}

🎯 ÖZEL TALİMAT: Yukarıdaki tespit edilen ürün yerleşimine göre değerlendirme yap!
Hangi ürünün hangi konumda olduğu belli, buna göre yan yana olan ürünleri kontrol et.
                """
                
                # Base64'e çevir (yüksek kalite)
                image_base64 = encode_image_to_base64(image_bytes, enhance_quality=True)
                
                # Azure OpenAI GPT-4.1 API çağrısı (detaylı bilgi ile)
                response = call_azure_openai_api(image_base64, enhanced_evaluation_prompt)
                
            except json.JSONDecodeError:
                raise HTTPException(status_code=400, detail="content_data geçersiz JSON formatında")
                
        else:
            # Sadece görüntü ile değerlendirme yap
            # Base64'e çevir (yüksek kalite)
            image_base64 = encode_image_to_base64(image_bytes, enhance_quality=True)
            
            # Azure OpenAI GPT-4.1 API çağrısı (standart)
            response = call_azure_openai_api(image_base64, EVALUATION_PROMPT)
        
        # JSON parse et
        result_data = parse_json_response(response)
        
        # Kullanılan modu belirt
        result_data["analiz_modu"] = "detayli_analiz" if content_data else "direkt_analiz"
        
        # Başarılı sonuç
        from datetime import datetime
        return AnalysisResponse(
            success=True,
            data=result_data,
            timestamp=datetime.now().isoformat()
        )
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)