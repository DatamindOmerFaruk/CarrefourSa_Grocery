"""
S3 Object Storage'dan görselleri alıp API'lara göndererek PostgreSQL'e yazan batch processor
"""
import os
import requests
import psycopg2
from psycopg2.extras import RealDictCursor
import json
import boto3
from botocore.exceptions import ClientError
from botocore.config import Config
from datetime import datetime, timedelta
# urllib3 SSL uyarılarını bastır (self-signed certificate için)
import urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
import logging
from typing import List, Dict, Any, Optional
import time
from urllib.parse import quote
from dotenv import load_dotenv
from pathlib import Path

# Ana klasördeki .env dosyasını yükle (2 seviye yukarı: manav_analiz -> doluluk&reyonsıralaması -> ana klasör)
current_file = Path(__file__).resolve()
root_dir = current_file.parent.parent.parent  # Ana klasöre git
env_file = root_dir / '.env'

# Ana klasördeki .env dosyasını yükle
if env_file.exists():
    load_dotenv(dotenv_path=env_file, override=True)
    print(f"✅ Ana klasördeki .env dosyası yüklendi: {env_file}")
else:
    # Eğer ana klasörde .env yoksa, mevcut dizinde ara (fallback)
    load_dotenv()
    print(f"⚠️  Ana klasörde .env bulunamadı ({env_file}), mevcut dizinde aranıyor...")

# AWS checksum hesaplama ve doğrulama için environment variable'ları ayarla
# Bu, bazı S3 uyumlu sistemlerde (Cohesity gibi) Content-Length sorunlarını çözebilir
os.environ.setdefault("AWS_REQUEST_CHECKSUM_CALCULATION", "when_required")
os.environ.setdefault("AWS_RESPONSE_CHECKSUM_VALIDATION", "when_required")

# Logging ayarları
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('batch_processor.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# === PostgreSQL Tablo DDL'leri ===
DDL_TABLES = """
-- Content analiz sonuçları tablosu
CREATE TABLE IF NOT EXISTS analyze_row (
    id BIGSERIAL PRIMARY KEY,
    source_url TEXT NOT NULL,
    ts TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    satir_sayisi INT,
    sutun_sayisi INT,
    toplam_kasa INT,
    row_index INT NOT NULL,
    konum TEXT NOT NULL,
    ana_urun TEXT NOT NULL,
    yan_urunler TEXT,
    raw JSONB NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_analyze_row_sourceurl ON analyze_row(source_url);
CREATE INDEX IF NOT EXISTS idx_analyze_row_ts ON analyze_row(ts);
CREATE INDEX IF NOT EXISTS idx_analyze_row_urun ON analyze_row(ana_urun);

-- Stock analiz sonuçları tablosu
CREATE TABLE IF NOT EXISTS analyze_stock_row (
    id BIGSERIAL PRIMARY KEY,
    source_url TEXT NOT NULL,
    ts TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    reyon_id TEXT NOT NULL,
    doluluk NUMERIC(6,4),
    durum TEXT,
    aciliyet TEXT,
    kasa_gorunurlugu BOOLEAN,
    doluluk_seviyeleri TEXT NOT NULL,
    raw JSONB NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_analyze_stock_row_source ON analyze_stock_row(source_url);
CREATE INDEX IF NOT EXISTS idx_analyze_stock_row_ts ON analyze_stock_row(ts);
CREATE INDEX IF NOT EXISTS idx_analyze_stock_row_durum ON analyze_stock_row(durum);
CREATE INDEX IF NOT EXISTS idx_analyze_stock_row_reyon ON analyze_stock_row(reyon_id);

-- Evaluation analiz sonuçları tablosu
CREATE TABLE IF NOT EXISTS analyze_evaluation_row (
    id BIGSERIAL PRIMARY KEY,
    source_url TEXT NOT NULL,
    ts TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    genel_skor NUMERIC(6,3),
    toplam_hata INT,
    kritik_hata INT,
    uyari INT,
    analiz_modu TEXT,
    hata_tipi TEXT,
    konum1 TEXT,
    urun1 TEXT,
    konum2 TEXT,
    urun2 TEXT,
    problem TEXT,
    oneri TEXT,
    olumlu_yerlesimler JSONB NOT NULL,
    genel_oneriler JSONB NOT NULL,
    raw JSONB NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_eval_row_source ON analyze_evaluation_row(source_url);
CREATE INDEX IF NOT EXISTS idx_eval_row_ts ON analyze_evaluation_row(ts);
CREATE INDEX IF NOT EXISTS idx_eval_row_tip ON analyze_evaluation_row(hata_tipi);
"""

class BatchProcessor:
    def __init__(self):
        """Konfigürasyonları yükle"""
        self.load_config()
        self.setup_connections()
        
    def load_config(self):
        """Çevre değişkenlerinden konfigürasyonları yükle"""
        # S3 Object Storage
        self.s3_endpoint_url = os.getenv('S3_ENDPOINT_URL', 'https://161cohesity.carrefoursa.com:3000')
        self.s3_access_key_id = os.getenv('S3_ACCESS_KEY_ID', 'sWxdTl3ERx7myBE1qpW06_haVvuhATcdsmBbqaWkXYU')
        self.s3_secret_access_key = os.getenv('S3_SECRET_ACCESS_KEY', 'Ti9Fonk3wYyG5PMx5LaGUmlcVyCuqsE5BLVV5vv8PU0')
        self.s3_bucket_name = os.getenv('S3_BUCKET_NAME', 'Grocery')
        
        # PostgreSQL
        self.pg_host = os.getenv('POSTGRES_HOST', '45.84.18.76')
        self.pg_port = os.getenv('POSTGRES_PORT', '5432')
        self.pg_database = os.getenv('POSTGRES_DB', 'postgres')  # Veritabanı adı: postgres
        self.pg_user = os.getenv('POSTGRES_USER', 'grocerryadmin')  # Kullanıcı adı: grocerryadmin
        self.pg_password = os.getenv('POSTGRES_PASSWORD', 'a08Iyr95vLHTYY')
        
        # Azure PostgreSQL kontrolü - Azure PostgreSQL kullanılmamalı, 45.84.18.76 kullanılmalı
        if 'database.azure.com' in self.pg_host.lower() or 'azure' in self.pg_host.lower():
            logger.error("=" * 60)
            logger.error("⚠️  UYARI: Azure PostgreSQL tespit edildi!")
            logger.error(f"Şu anki host: {self.pg_host}")
            logger.error("Lütfen 45.84.18.76 IP'li veritabanını kullanın.")
            logger.error("=" * 60)
            logger.error("POSTGRES_HOST=45.84.18.76 olarak ayarlayın (.env dosyasında)")
            raise ValueError(
                f"Azure PostgreSQL kullanılamaz! Lütfen 45.84.18.76 IP'li veritabanını kullanın. "
                f"Şu anki host: {self.pg_host}"
            )
        
        # Database adı kontrolü - sadece 'postgres' olmalı
        if self.pg_database.lower() != 'postgres':
            logger.warning(f"⚠️  Database adı 'postgres' değil: {self.pg_database}")
            logger.warning("POSTGRES_DB=postgres olarak ayarlayın (.env dosyasında)")
        
        # API Endpoints
        self.api_base_url = os.getenv('API_BASE_URL', 'http://localhost:8000')
        self.test_mode = os.getenv('TEST_MODE', 'false').lower() == 'true'
        
        # API URL kontrolü - localhost yerine 127.0.0.1 veya gerçek IP kullanılmalı
        if 'localhost' in self.api_base_url.lower():
            logger.warning(f"⚠️  API_BASE_URL localhost kullanıyor: {self.api_base_url}")
            logger.warning("Linux sunucuda localhost yerine 127.0.0.1 veya gerçek IP kullanın")
            logger.warning("Örnek: API_BASE_URL=http://127.0.0.1:8000 veya API_BASE_URL=http://45.84.18.76:8000")
        
        # Batch ayarları
        self.batch_size = int(os.getenv('BATCH_SIZE', '10'))
        self.retry_count = int(os.getenv('RETRY_COUNT', '3'))
        self.delay_between_requests = float(os.getenv('REQUEST_DELAY', '1.0'))
        
        # Bağlantı bilgilerini log'a yazdır
        logger.info(f"PostgreSQL Host: {self.pg_host}:{self.pg_port}")
        logger.info(f"PostgreSQL Database: {self.pg_database}")
        logger.info(f"PostgreSQL User: {self.pg_user}")
        logger.info(f"API Base URL: {self.api_base_url}")
        
        if not all([self.s3_access_key_id, self.s3_secret_access_key, self.pg_database, self.pg_user, self.pg_password]):
            raise ValueError("Gerekli çevre değişkenleri eksik!")
            
    def setup_connections(self):
        """S3 ve PostgreSQL bağlantılarını kur"""
        try:
            # S3 Client
            self.s3_client = boto3.client(
                "s3",
                endpoint_url=self.s3_endpoint_url,
                aws_access_key_id=self.s3_access_key_id,
                aws_secret_access_key=self.s3_secret_access_key,
                verify=False,  # self-signed için
                config=Config(
                    signature_version="s3v4",
                    s3={"addressing_style": "path"},  # ÖNEMLİ: path style
                ),
            )
            
            # PostgreSQL bağlantısı
            # sslmode=prefer: SSL varsa kullanır, yoksa SSL olmadan bağlanır
            logger.info(f"PostgreSQL'ye bağlanılıyor: {self.pg_host}:{self.pg_port}/{self.pg_database} (user: {self.pg_user})")
            self.pg_connection = psycopg2.connect(
                host=self.pg_host,
                port=self.pg_port,
                database=self.pg_database,
                user=self.pg_user,
                password=self.pg_password,
                sslmode='prefer'  # SSL desteklenmiyorsa otomatik olarak SSL olmadan bağlanır
            )
            self.pg_connection.autocommit = True
            
            logger.info(f"✅ PostgreSQL bağlantısı başarılı: {self.pg_host}:{self.pg_port}/{self.pg_database}")
            
            # Tabloları oluştur
            self.ensure_tables()
            
            logger.info("S3 Object Storage ve PostgreSQL bağlantıları başarılı")
            
            # API health check
            self.check_api_health()
            
        except Exception as e:
            logger.error(f"Bağlantı hatası: {str(e)}")
            raise
    
    def ensure_tables(self):
        """Veritabanında gerekli tabloları oluşturur"""
        try:
            with self.pg_connection.cursor() as cursor:
                # DDL'deki her statement'ı ayrı ayrı çalıştır
                # Önce CREATE TABLE statement'larını, sonra CREATE INDEX statement'larını çalıştır
                ddl_lines = DDL_TABLES.split('\n')
                current_statement = []
                statements = []
                
                for line in ddl_lines:
                    line_stripped = line.strip()
                    # Yorumları atla
                    if line_stripped.startswith('--') or not line_stripped:
                        continue
                    
                    current_statement.append(line)
                    # Statement sonu (; ile bitiyor)
                    if line_stripped.endswith(';'):
                        statement = ' '.join(current_statement)
                        statements.append(statement)
                        current_statement = []
                
                # Her statement'ı çalıştır
                for statement in statements:
                    if statement.strip():
                        try:
                            cursor.execute(statement)
                        except Exception as e:
                            error_str = str(e).lower()
                            # Tablo/index zaten varsa - göz ardı et
                            if any(keyword in error_str for keyword in ['already exists', 'duplicate', 'relation already']):
                                pass  # Sessizce geç
                            else:
                                # Diğer hatalar için uyarı ver
                                logger.warning(f"DDL statement hatası (devam ediliyor): {str(e)[:150]}")
                                logger.debug(f"Statement: {statement[:100]}...")
                                
            logger.info("✅ Veritabanı tabloları kontrol edildi/oluşturuldu")
        except Exception as e:
            logger.error(f"Tablo oluşturma hatası: {str(e)}")
            # Sadece kritik hatalar için raise et
            if 'does not exist' in str(e).lower():
                logger.warning("Tablo yapısı uyumsuz olabilir. Lütfen tabloları kontrol edin.")
            else:
                raise
    
    def check_api_health(self) -> bool:
        """API'nin çalışıp çalışmadığını kontrol et. Başarılıysa True, başarısızsa False döndür."""
        try:
            health_url = f"{self.api_base_url}/health"
            logger.info(f"API health check: {health_url}")
            
            # SSL uyarılarını bastır
            response = requests.get(health_url, timeout=5, verify=False)
            
            if response.status_code == 200:
                logger.info("✅ API sağlık kontrolü başarılı")
                return True
            else:
                logger.warning(f"API health check başarısız: Status {response.status_code}")
                return False
        except requests.exceptions.ConnectionError as e:
            logger.error("=" * 60)
            logger.error(f"❌ API'ye bağlanılamıyor: {self.api_base_url}")
            logger.error("=" * 60)
            logger.error("Lütfen API'nin çalıştığından emin olun (systemd service: manav-api)")
            logger.error("")
            logger.error("API kontrolü için:")
            logger.error("  sudo systemctl status manav-api")
            logger.error("")
            logger.error("API başlatmak için:")
            logger.error("  sudo systemctl start manav-api")
            logger.error("")
            logger.error("API yeniden başlatmak için (SSL düzeltmesi için gerekli):")
            logger.error("  sudo systemctl restart manav-api")
            logger.error("")
            logger.error("API loglarını kontrol etmek için:")
            logger.error("  sudo journalctl -u manav-api -f")
            logger.error("=" * 60)
            return False
        except Exception as e:
            logger.warning(f"API health check hatası: {str(e)}")
            return False
            
    def get_all_images(self) -> List[Dict[str, str]]:
        """
        S3 Object Storage'dan sadece genel reyon görüntülerini listele
        
        cameras_reyon_genel.yaml'dan alınan fotoğraflar S3'te şu formatta kaydedilir:
        snapshots/genel_gorunum/camera_XXX/YYYY-MM-DD/HH/genel_gorunum_X_timestamp.jpg
        
        Lokal path: snapshots/reyon_genel/camera_XXX/...
        S3 path: snapshots/genel_gorunum/camera_XXX/... (genel görünüm klasörü altında)
        """
        try:
            # S3'ten sadece genel_gorunum klasöründeki görselleri listele
            prefix = "snapshots/genel_gorunum/"
            blobs = []
            
            paginator = self.s3_client.get_paginator('list_objects_v2')
            pages = paginator.paginate(Bucket=self.s3_bucket_name, Prefix=prefix)
            
            for page in pages:
                if 'Contents' in page:
                    for obj in page['Contents']:
                        obj_key = obj['Key']
                        # Sadece resim dosyalarını al
                        if obj_key.lower().endswith(('.jpg', '.jpeg', '.png', '.bmp', '.gif')):
                            # S3 URL oluştur
                            if self.s3_endpoint_url.endswith('/'):
                                s3_url = f"{self.s3_endpoint_url}{self.s3_bucket_name}/{obj_key}"
                            else:
                                s3_url = f"{self.s3_endpoint_url}/{self.s3_bucket_name}/{obj_key}"
                            
                            blobs.append({
                                'name': obj_key,
                                'url': s3_url,
                                'sas_url': s3_url,  # S3'te SAS token gerekmez, direkt URL kullanılır
                                'folder': '/'.join(obj_key.split('/')[:-1]) if '/' in obj_key else '',
                                'size': obj.get('Size', 0),
                                'last_modified': obj.get('LastModified')
                            })
                    
            logger.info(f"Toplam {len(blobs)} genel reyon görseli bulundu (snapshots/genel_gorunum/ klasöründen)")
            logger.info(f"S3 path formatı: snapshots/genel_gorunum/camera_XXX/YYYY-MM-DD/HH/genel_gorunum_X_timestamp.jpg")
            return blobs
            
        except Exception as e:
            logger.error(f"S3 Object Storage'dan dosya listesi alınamadı: {str(e)}")
            raise
            
    def download_image(self, s3_key: str) -> bytes:
        """Görseli S3 Object Storage'dan indir"""
        try:
            response = self.s3_client.get_object(Bucket=self.s3_bucket_name, Key=s3_key)
            return response['Body'].read()
            
        except ClientError as e:
            logger.error(f"Görsel indirilemedi ({s3_key}): {str(e)}")
            raise
            
    def call_api(self, endpoint: str, image_bytes: bytes, additional_data: Dict = None) -> Dict:
        """API endpoint'ine görsel gönder"""
        url = f"{self.api_base_url}/{endpoint}"
        
        files = {'file': ('image.jpg', image_bytes, 'image/jpeg')}
        data = additional_data or {}
        
        for attempt in range(self.retry_count):
            try:
                logger.info(f"API çağrısı: {url}")
                response = requests.post(url, files=files, data=data, timeout=120)
                logger.info(f"Response status: {response.status_code}")
                if response.status_code != 200:
                    logger.error(f"Response content: {response.text}")
                response.raise_for_status()
                return response.json()
                
            except Exception as e:
                logger.warning(f"API çağrısı başarısız (deneme {attempt + 1}/{self.retry_count}): {str(e)}")
                if attempt == self.retry_count - 1:
                    raise
    def call_api_with_url(self, endpoint: str, image_url: str, additional_data: Dict = None) -> Dict:
        """API endpoint'ine S3 URL gönder"""
        url = f"{self.api_base_url}/{endpoint}"
        
        data = {'image_url': image_url}
        if additional_data:
            data.update(additional_data)
        
        for attempt in range(self.retry_count):
            try:
                logger.info(f"API çağrısı: {url} with URL: {image_url[:100]}...")
                response = requests.post(url, data=data, timeout=120)
                logger.info(f"Response status: {response.status_code}")
                if response.status_code != 200:
                    logger.error(f"Response content: {response.text}")
                response.raise_for_status()
                return response.json()
                
            except Exception as e:
                logger.warning(f"API çağrısı başarısız (deneme {attempt + 1}/{self.retry_count}): {str(e)}")
                if attempt == self.retry_count - 1:
                    raise
                time.sleep(2 ** attempt)  # Exponential backoff
                
    def process_content_api(self, sas_url: str, source_url: str) -> Dict:
        """Content API'yi SAS URL ile çağır"""
        try:
            result = self.call_api_with_url('analyze/content', sas_url)
            
            if not result.get('success'):
                raise Exception(f"API hatası: {result.get('error', 'Bilinmeyen hata')}")
                
            return {
                'success': True,
                'data': result['data'],
                'timestamp': result['timestamp']
            }
            
        except Exception as e:
            logger.error(f"Content API hatası ({source_url}): {str(e)}")
            return {'success': False, 'error': str(e)}
            
    def process_stock_api(self, sas_url: str, source_url: str) -> Dict:
        """Stock API'yi SAS URL ile çağır"""
        try:
            result = self.call_api_with_url('analyze/stock', sas_url)
            
            if not result.get('success'):
                raise Exception(f"API hatası: {result.get('error', 'Bilinmeyen hata')}")
                
            return {
                'success': True,
                'data': result['data'],
                'timestamp': result['timestamp']
            }
            
        except Exception as e:
            logger.error(f"Stock API hatası ({source_url}): {str(e)}")
            return {'success': False, 'error': str(e)}
            
    def process_evaluation_api(self, sas_url: str, source_url: str, content_data: Dict = None) -> Dict:
        """Evaluation API'yi SAS URL ile çağır"""
        try:
            additional_data = {}
            if content_data and content_data.get('success'):
                additional_data['content_data'] = json.dumps(content_data['data'])
                
            result = self.call_api_with_url('analyze/evaluation', sas_url, additional_data)
            
            if not result.get('success'):
                raise Exception(f"API hatası: {result.get('error', 'Bilinmeyen hata')}")
                
            return {
                'success': True,
                'data': result['data'],
                'timestamp': result['timestamp']
            }
            
        except Exception as e:
            logger.error(f"Evaluation API hatası ({source_url}): {str(e)}")
            return {'success': False, 'error': str(e)}
            
    def save_content_results(self, source_url: str, content_data: Dict):
        """Content sonuçlarını analyze_row tablosuna kaydet"""
        if not content_data.get('success'):
            return
            
        try:
            data = content_data['data']
            grid_info = data.get('grid_bilgisi', {})
            tablo_format = data.get('tablo_format', {})
            satirlar = tablo_format.get('satirlar', [])
            
            with self.pg_connection.cursor() as cursor:
                inserted_count = 0
                for idx, satir in enumerate(satirlar):
                    # NOT NULL alanlar için varsayılan değerler
                    konum = satir.get('konum', '') or 'Bilinmeyen'
                    ana_urun = satir.get('ana_urun', '') or 'Bilinmeyen'
                    
                    try:
                        cursor.execute("""
                            INSERT INTO analyze_row (
                                source_url, satir_sayisi, sutun_sayisi, toplam_kasa,
                                row_index, konum, ana_urun, yan_urunler, raw
                            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                        """, (
                            source_url,
                            grid_info.get('satir_sayisi'),
                            grid_info.get('sutun_sayisi'),
                            grid_info.get('toplam_kasa'),
                            idx,
                            konum,
                            ana_urun,
                            satir.get('yan_urunler', ''),
                            json.dumps(data, ensure_ascii=False)
                        ))
                        inserted_count += cursor.rowcount
                        logger.debug(f"Content satır {idx} kaydedildi: {konum} - {ana_urun}")
                    except Exception as row_error:
                        logger.error(f"Content satır {idx} kaydetme hatası: {str(row_error)}")
                        logger.error(f"  Konum: {konum}, Ana ürün: {ana_urun}")
                        raise
                    
            # Commit kontrolü (autocommit=True olsa bile)
            self.pg_connection.commit()
            logger.info(f"✅ VERİTABANI: Content sonuçları kaydedildi ({self.pg_host}/{self.pg_database})")
            logger.info(f"   - Tablo: analyze_row")
            logger.info(f"   - Kayıt sayısı: {inserted_count}/{len(satirlar)} satır")
            
        except Exception as e:
            logger.error(f"❌ Content kaydetme hatası: {str(e)}")
            logger.error(f"   Source URL: {source_url[:100]}")
            import traceback
            logger.error(traceback.format_exc())
            raise
            
    def save_stock_results(self, source_url: str, stock_data: Dict):
        """Stock sonuçlarını analyze_stock_row tablosuna kaydet - BASİT METİN FORMAT"""
        if not stock_data.get('success'):
            return
            
        try:
            data = stock_data['data']
            reyon_durumlari = data.get('reyon_durumları', [])
            ozet = data.get('özet', {})
            
            # Basit metin özeti oluştur
            dolu_reyonlar = []
            normal_reyonlar = []
            kritik_reyonlar = []
            bos_reyonlar = []
            
            for reyon in reyon_durumlari:
                urun = reyon.get('ürün', '')
                konum = reyon.get('konum', '')
                durum = reyon.get('durum', '')
                
                if durum == 'dolu':
                    dolu_reyonlar.append(f"{urun} ({konum})")
                elif durum == 'normal':
                    normal_reyonlar.append(f"{urun} ({konum})")
                elif durum == 'kritik':
                    kritik_reyonlar.append(f"{urun} ({konum})")
                elif durum == 'boş':
                    bos_reyonlar.append(f"Boş kasa ({konum})")
            
            # Basit metin özeti
            doluluk_ozeti = []
            if dolu_reyonlar:
                doluluk_ozeti.append(f"DOLU: {', '.join(dolu_reyonlar)}")
            if normal_reyonlar:
                doluluk_ozeti.append(f"NORMAL: {', '.join(normal_reyonlar)}")
            if kritik_reyonlar:
                doluluk_ozeti.append(f"KRİTİK: {', '.join(kritik_reyonlar)}")
            if bos_reyonlar:
                doluluk_ozeti.append(f"BOŞ: {', '.join(bos_reyonlar)}")
            
            doluluk_metni = " | ".join(doluluk_ozeti) if doluluk_ozeti else "Veri yok"
            reyon_id = f"Toplam {ozet.get('toplam_kasa', len(reyon_durumlari))} kasa"
            
            logger.debug(f"Stock kayıt hazırlanıyor: reyon_id={reyon_id}, doluluk_metni={doluluk_metni[:50]}...")
            
            inserted_count = 0
            with self.pg_connection.cursor() as cursor:
                # Tek bir satır olarak kaydet (özet)
                try:
                    cursor.execute("""
                        INSERT INTO analyze_stock_row (
                            source_url, reyon_id, doluluk, durum, aciliyet,
                            kasa_gorunurlugu, doluluk_seviyeleri, raw
                        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                    """, (
                        source_url,
                        reyon_id,
                        None,  # Doluluk oranı (NUMERIC(6,4))
                        f"Dolu:{ozet.get('dolu_kasa', 0)} Normal:{ozet.get('normal_kasa', 0)} Kritik:{ozet.get('kritik_kasa', 0)} Boş:{ozet.get('boş_kasa', 0)}",
                        'orta' if ozet.get('kritik_kasa', 0) > 0 or ozet.get('boş_kasa', 0) > 0 else 'düşük',
                        True,
                        doluluk_metni,  # NOT NULL - BASİT METİN FORMAT!
                        json.dumps(data, ensure_ascii=False)
                    ))
                    inserted_count = cursor.rowcount
                    logger.debug(f"Stock INSERT başarılı, rowcount: {inserted_count}")
                except Exception as insert_error:
                    logger.error(f"❌ Stock INSERT hatası: {str(insert_error)}")
                    logger.error(f"   Source URL: {source_url[:100]}")
                    logger.error(f"   Reyon ID: {reyon_id}")
                    logger.error(f"   Doluluk metni uzunluğu: {len(doluluk_metni)}")
                    import traceback
                    logger.error(traceback.format_exc())
                    raise
                    
            # Commit kontrolü (autocommit=True olsa bile)
            self.pg_connection.commit()
            logger.info(f"✅ VERİTABANI: Stock sonuçları kaydedildi ({self.pg_host}/{self.pg_database})")
            logger.info(f"   - Tablo: analyze_stock_row")
            logger.info(f"   - Kayıt sayısı: {inserted_count} satır")
            logger.info(f"   - Reyon sayısı: {len(reyon_durumlari)} reyon")
            logger.info(f"   - Doluluk özeti: {doluluk_metni[:100]}...")
            
        except Exception as e:
            logger.error(f"❌ Stock kaydetme hatası: {str(e)}")
            logger.error(f"   Source URL: {source_url[:100]}")
            import traceback
            logger.error(traceback.format_exc())
            raise
            
    def save_evaluation_results(self, source_url: str, evaluation_data: Dict):
        """Evaluation sonuçlarını analyze_evaluation_row tablosuna kaydet"""
        if not evaluation_data.get('success'):
            return
            
        try:
            data = evaluation_data['data']
            degerlendirme = data.get('degerlendirme_sonucu', {})
            hatalar = data.get('tespit_edilen_hatalar', [])
            olumlu_yerlesimler = data.get('olumlu_yerlesimler', [])
            genel_oneriler = data.get('genel_oneriler', [])
            analiz_modu = data.get('analiz_modu', '')
            
            # NOT NULL alanlar için varsayılan değerler
            olumlu_yerlesimler_json = json.dumps(olumlu_yerlesimler if olumlu_yerlesimler else [], ensure_ascii=False)
            genel_oneriler_json = json.dumps(genel_oneriler if genel_oneriler else [], ensure_ascii=False)
            raw_json = json.dumps(data, ensure_ascii=False)
            
            logger.debug(f"Evaluation kayıt hazırlanıyor: {len(hatalar)} hata, genel_skor={degerlendirme.get('genel_skor')}")
            
            with self.pg_connection.cursor() as cursor:
                inserted_count = 0
                if hatalar:
                    # Her hata için ayrı satır
                    for idx, hata in enumerate(hatalar):
                        try:
                            cursor.execute("""
                                INSERT INTO analyze_evaluation_row (
                                    source_url, genel_skor, toplam_hata, kritik_hata, uyari,
                                    analiz_modu, hata_tipi, konum1, urun1, konum2, urun2,
                                    problem, oneri, olumlu_yerlesimler, genel_oneriler, raw
                                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                            """, (
                                source_url,
                                degerlendirme.get('genel_skor'),
                                degerlendirme.get('toplam_hata'),
                                degerlendirme.get('kritik_hata'),
                                degerlendirme.get('uyari'),
                                analiz_modu,
                                hata.get('hata_tipi'),
                                hata.get('konum1'),
                                hata.get('urun1'),
                                hata.get('konum2'),
                                hata.get('urun2'),
                                hata.get('problem'),
                                hata.get('oneri'),
                                olumlu_yerlesimler_json,  # NOT NULL
                                genel_oneriler_json,  # NOT NULL
                                raw_json  # NOT NULL
                            ))
                            inserted_count += cursor.rowcount
                            logger.debug(f"Evaluation hata {idx} kaydedildi: {hata.get('hata_tipi')}")
                        except Exception as row_error:
                            logger.error(f"❌ Evaluation hata {idx} kaydetme hatası: {str(row_error)}")
                            logger.error(f"   Hata tipi: {hata.get('hata_tipi')}")
                            raise
                else:
                    # Hata yoksa tek satır
                    try:
                        cursor.execute("""
                            INSERT INTO analyze_evaluation_row (
                                source_url, genel_skor, toplam_hata, kritik_hata, uyari,
                                analiz_modu, olumlu_yerlesimler, genel_oneriler, raw
                            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                        """, (
                            source_url,
                            degerlendirme.get('genel_skor'),
                            degerlendirme.get('toplam_hata'),
                            degerlendirme.get('kritik_hata'),
                            degerlendirme.get('uyari'),
                            analiz_modu,
                            olumlu_yerlesimler_json,  # NOT NULL
                            genel_oneriler_json,  # NOT NULL
                            raw_json  # NOT NULL
                        ))
                        inserted_count = cursor.rowcount
                        logger.debug(f"Evaluation (hata yok) kaydedildi, rowcount: {inserted_count}")
                    except Exception as insert_error:
                        logger.error(f"❌ Evaluation INSERT hatası: {str(insert_error)}")
                        logger.error(f"   Source URL: {source_url[:100]}")
                        import traceback
                        logger.error(traceback.format_exc())
                        raise
                    
            # Commit kontrolü (autocommit=True olsa bile)
            self.pg_connection.commit()
            logger.info(f"✅ VERİTABANI: Evaluation sonuçları kaydedildi ({self.pg_host}/{self.pg_database})")
            logger.info(f"   - Tablo: analyze_evaluation_row")
            logger.info(f"   - Kayıt sayısı: {inserted_count} satır")
            logger.info(f"   - Genel skor: {degerlendirme.get('genel_skor', 'N/A')}")
            logger.info(f"   - Toplam hata: {degerlendirme.get('toplam_hata', 0)}, Kritik: {degerlendirme.get('kritik_hata', 0)}")
            
        except Exception as e:
            logger.error(f"❌ Evaluation kaydetme hatası: {str(e)}")
            logger.error(f"   Source URL: {source_url[:100]}")
            import traceback
            logger.error(traceback.format_exc())
            raise
            
    def process_single_image_stock_only(self, blob_info: Dict) -> Dict:
        """Tek görseli işle - STOCK + EVALUATION ANALİZİ (Problem çıktıları için)"""
        s3_url = blob_info['sas_url']  # S3 URL'i source_url olarak kullan
        blob_name = blob_info['name']
        
        logger.info(f"Stock + Evaluation analizi: {blob_name}")
        logger.info(f"S3 URL: {s3_url[:100]}...")
        
        try:
            # Stock API'sini çağır
            stock_result = self.process_stock_api(s3_url, s3_url)
            
            # API başarısızsa hata döndür
            if not stock_result.get('success', False):
                error_msg = stock_result.get('error', 'Bilinmeyen hata')
                logger.error(f"Stock API başarısız ({blob_name}): {error_msg}")
                return {
                    'success': False,
                    'blob_name': blob_name,
                    'source_url': s3_url,
                    'error': error_msg,
                    'stock_success': False
                }
            
            # Stock sonuçlarını kaydet
            logger.info(f"✅ Stock API başarılı, veritabanına kaydediliyor...")
            self.save_stock_results(s3_url, stock_result)
            
            # Evaluation API'sini de çağır (problem çıktıları için)
            time.sleep(self.delay_between_requests)
            logger.info(f"Evaluation analizi başlatılıyor (problem çıktıları için)...")
            evaluation_result = self.process_evaluation_api(s3_url, s3_url, content_data=None)
            
            # Evaluation sonuçlarını kaydet
            if evaluation_result.get('success', False):
                logger.info(f"✅ Evaluation API başarılı, veritabanına kaydediliyor...")
                self.save_evaluation_results(s3_url, evaluation_result)
                logger.info(f"✅ Veritabanına kayıt tamamlandı: {blob_name} (Stock + Evaluation)")
            else:
                logger.warning(f"⚠️  Evaluation API başarısız, sadece Stock kaydedildi")
            
            return {
                'success': True,
                'blob_name': blob_name,
                'source_url': s3_url,
                'stock_success': True,
                'evaluation_success': evaluation_result.get('success', False)
            }
            
        except Exception as e:
            logger.error(f"Stock analizi hatası ({blob_name}): {str(e)}")
            return {
                'success': False,
                'blob_name': blob_name,
                'source_url': s3_url,
                'error': str(e),
                'stock_success': False
            }

    def process_single_image(self, blob_info: Dict) -> Dict:
        """Tek görseli işle - S3 URL ile"""
        s3_url = blob_info['sas_url']  # S3 URL'i source_url olarak kullan
        blob_name = blob_info['name']
        
        logger.info(f"İşleniyor: {blob_name}")
        logger.info(f"S3 URL source_url olarak kaydedilecek: {s3_url[:100]}...")
        
        try:
            # API'leri sırayla çağır (S3 URL ile)
            content_result = self.process_content_api(s3_url, s3_url)
            time.sleep(self.delay_between_requests)
            
            stock_result = self.process_stock_api(s3_url, s3_url)
            time.sleep(self.delay_between_requests)
            
            evaluation_result = self.process_evaluation_api(
                s3_url, s3_url, content_result
            )
            
            # Sonuçları kaydet (S3 URL'i source_url olarak)
            self.save_content_results(s3_url, content_result)
            self.save_stock_results(s3_url, stock_result)
            self.save_evaluation_results(s3_url, evaluation_result)
            
            return {
                'success': True,
                'blob_name': blob_name,
                'source_url': s3_url,
                'content_success': content_result.get('success', False),
                'stock_success': stock_result.get('success', False),
                'evaluation_success': evaluation_result.get('success', False)
            }
            
        except Exception as e:
            logger.error(f"Görsel işleme hatası ({blob_name}): {str(e)}")
            return {
                'success': False,
                'blob_name': blob_name,
                'source_url': s3_url,
                'error': str(e)
            }
            
    def run_batch_processing(self):
        """Ana batch işlem döngüsü"""
        logger.info("Batch işlemi başlatılıyor...")
        
        # API sağlık kontrolü
        if not self.check_api_health():
            logger.error("=" * 60)
            logger.error("API'ye bağlanılamadı! İşlem durduruluyor.")
            logger.error("=" * 60)
            logger.error("Lütfen API'yi başlatın ve tekrar deneyin:")
            logger.error("  sudo systemctl start manav-api")
            logger.error("  sudo systemctl status manav-api")
            raise ConnectionError(f"API'ye bağlanılamıyor: {self.api_base_url}")
        
        try:
            # Tüm görselleri listele
            all_images = self.get_all_images()
            
            if not all_images:
                logger.warning("İşlenecek görsel bulunamadı")
                return
                
            # İstatistikler
            total_images = len(all_images)
            processed = 0
            successful = 0
            failed = 0
            
            logger.info(f"Toplam {total_images} görsel işlenecek")
            
            # Batch'ler halinde işle
            for i in range(0, total_images, self.batch_size):
                batch = all_images[i:i + self.batch_size]
                batch_num = (i // self.batch_size) + 1
                
                logger.info(f"Batch {batch_num} işleniyor ({len(batch)} görsel)")
                
                for blob_info in batch:
                    result = self.process_single_image(blob_info)
                    processed += 1
                    
                    if result['success']:
                        successful += 1
                        logger.info(f"[OK] {result['blob_name']} başarılı ({processed}/{total_images})")
                    else:
                        failed += 1
                        logger.error(f"[FAIL] {result['blob_name']} başarısız ({processed}/{total_images})")
                        
                    # Progress raporu
                    if processed % 10 == 0:
                        progress = (processed / total_images) * 100
                        logger.info(f"İlerleme: {progress:.1f}% ({processed}/{total_images})")
                        
                # Batch arası bekleme
                if i + self.batch_size < total_images:
                    logger.info(f"Batch tamamlandı, {self.delay_between_requests}s bekleniyor...")
                    time.sleep(self.delay_between_requests)
                    
            # Final rapor
            logger.info("=" * 60)
            logger.info("BATCH İŞLEMİ TAMAMLANDI")
            logger.info(f"Toplam işlenen: {processed}")
            logger.info(f"Başarılı: {successful}")
            logger.info(f"Başarısız: {failed}")
            logger.info(f"Başarı oranı: {(successful/processed)*100:.1f}%")
            logger.info("=" * 60)
            
        except Exception as e:
            logger.error(f"Batch işlemi genel hatası: {str(e)}")
            raise
            
    def run_stock_only_processing(self):
        """STOCK + EVALUATION ANALİZİ için batch işlem döngüsü (Problem çıktıları ile)"""
        logger.info("Stock + Evaluation Batch işlemi başlatılıyor...")
        
        # API sağlık kontrolü
        if not self.check_api_health():
            logger.error("=" * 60)
            logger.error("API'ye bağlanılamadı! İşlem durduruluyor.")
            logger.error("=" * 60)
            logger.error("Lütfen API'yi başlatın ve tekrar deneyin:")
            logger.error("  sudo systemctl start manav-api")
            logger.error("  sudo systemctl status manav-api")
            raise ConnectionError(f"API'ye bağlanılamıyor: {self.api_base_url}")
        
        try:
            # Tüm görselleri listele
            all_images = self.get_all_images()
            
            if not all_images:
                logger.warning("İşlenecek görsel bulunamadı")
                return
                
            # İstatistikler
            total_images = len(all_images)
            processed = 0
            successful = 0
            failed = 0
            
            logger.info(f"Toplam {total_images} görsel STOCK + EVALUATION ANALİZİ için işlenecek")
            
            # Batch'ler halinde işle
            for i in range(0, total_images, self.batch_size):
                batch = all_images[i:i + self.batch_size]
                batch_num = (i // self.batch_size) + 1
                
                logger.info(f"Stock Batch {batch_num} işleniyor ({len(batch)} görsel)")
                
                for blob_info in batch:
                    result = self.process_single_image_stock_only(blob_info)
                    processed += 1
                    
                    if result['success']:
                        successful += 1
                        stock_status = "✅" if result.get('stock_success') else "❌"
                        eval_status = "✅" if result.get('evaluation_success') else "❌"
                        logger.info(f"[STOCK {stock_status} | EVAL {eval_status}] {result['blob_name']} başarılı ({processed}/{total_images})")
                    else:
                        failed += 1
                        logger.error(f"[STOCK FAIL] {result['blob_name']} başarısız ({processed}/{total_images})")
                        
                    # Progress raporu
                    if processed % 10 == 0:
                        progress = (processed / total_images) * 100
                        logger.info(f"Stock İlerleme: {progress:.1f}% ({processed}/{total_images})")
                        
                    # Request arası kısa bekleme
                    time.sleep(1)
                        
                # Batch arası bekleme
                if i + self.batch_size < total_images:
                    logger.info(f"Stock Batch tamamlandı, {self.delay_between_requests}s bekleniyor...")
                    time.sleep(self.delay_between_requests)
                    
            # Final rapor
            logger.info("=" * 60)
            logger.info("STOCK + EVALUATION BATCH İŞLEMİ TAMAMLANDI")
            logger.info(f"Toplam işlenen: {processed}")
            logger.info(f"Başarılı: {successful}")
            logger.info(f"Başarısız: {failed}")
            logger.info(f"Başarı oranı: {(successful/processed)*100:.1f}%")
            logger.info("=" * 60)
            
        except Exception as e:
            logger.error(f"Stock batch işlemi genel hatası: {str(e)}")
            raise
            
    def close_connections(self):
        """Bağlantıları kapat"""
        try:
            if hasattr(self, 'pg_connection'):
                self.pg_connection.close()
            logger.info("Bağlantılar kapatıldı")
        except Exception as e:
            logger.error(f"Bağlantı kapatma hatası: {str(e)}")


def main():
    """Ana fonksiyon"""
    processor = None
    
    try:
        processor = BatchProcessor()
        
        # Kullanıcıdan mode seçimi
        print("\n🔍 Batch Processor Modları:")
        print("1. Tam Analiz (Content + Stock + Evaluation)")
        print("2. Stock + Evaluation Analizi (Hızlı - Problem çıktıları ile)")
        
        while True:
            choice = input("\nHangi modu çalıştırmak istiyorsun? (1/2): ").strip()
            if choice == "1":
                logger.info("TAM ANALİZ modu seçildi (Content + Stock + Evaluation)")
                processor.run_batch_processing()
                break
            elif choice == "2":
                logger.info("STOCK + EVALUATION modu seçildi (Problem çıktıları ile)")
                processor.run_stock_only_processing()
                break
            else:
                print("❌ Geçersiz seçim! 1 veya 2 girin.")
        
    except KeyboardInterrupt:
        logger.info("İşlem kullanıcı tarafından durduruldu")
        
    except Exception as e:
        logger.error(f"Ana işlem hatası: {str(e)}")
        raise
        
    finally:
        if processor:
            processor.close_connections()


if __name__ == "__main__":
    main()