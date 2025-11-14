"""
Azure Storage'dan görselleri alıp API'lara göndererek PostgreSQL'e yazan batch processor
"""
import os
import requests
import psycopg2
from psycopg2.extras import RealDictCursor
import json
from azure.storage.blob import BlobServiceClient, generate_blob_sas, BlobSasPermissions
from datetime import datetime, timedelta
import logging
from typing import List, Dict, Any, Optional
import time
from urllib.parse import quote
from dotenv import load_dotenv

# .env dosyasını yükle
load_dotenv()

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

class BatchProcessor:
    def __init__(self):
        """Konfigürasyonları yükle"""
        self.load_config()
        self.setup_connections()
        
    def load_config(self):
        """Çevre değişkenlerinden konfigürasyonları yükle"""
        # Azure Storage
        self.azure_connection_string = os.getenv('AZURE_STORAGE_CONNECTION_STRING')
        self.container_name = os.getenv('AZURE_CONTAINER_NAME', 'snapshot')
        self.sas_token = os.getenv('AZURE_SAS_TOKEN')
        
        # Connection string'den account name'i çıkar
        conn_parts = dict(x.split('=', 1) for x in self.azure_connection_string.split(';') if '=' in x)
        self.account_name = conn_parts.get('AccountName')
        
        # PostgreSQL
        self.pg_host = os.getenv('POSTGRES_HOST', '45.84.18.76')
        self.pg_port = os.getenv('POSTGRES_PORT', '5432')
        self.pg_database = os.getenv('POSTGRES_DB', 'grocerryadmin')
        self.pg_user = os.getenv('POSTGRES_USER', 'grocerryadmin')
        self.pg_password = os.getenv('POSTGRES_PASSWORD', 'a08Iyr95vLHTYY')
        
        # API Endpoints
        self.api_base_url = os.getenv('API_BASE_URL', 'http://localhost:8000')
        self.test_mode = os.getenv('TEST_MODE', 'false').lower() == 'true'
        
        # Batch ayarları
        self.batch_size = int(os.getenv('BATCH_SIZE', '10'))
        self.retry_count = int(os.getenv('RETRY_COUNT', '3'))
        self.delay_between_requests = float(os.getenv('REQUEST_DELAY', '1.0'))
        
        if not all([self.azure_connection_string, self.pg_database, self.pg_user, self.pg_password]):
            raise ValueError("Gerekli çevre değişkenleri eksik!")
            
    def setup_connections(self):
        """Azure ve PostgreSQL bağlantılarını kur"""
        try:
            # Azure Blob Service Client
            self.blob_service_client = BlobServiceClient.from_connection_string(
                self.azure_connection_string
            )
            
            # PostgreSQL bağlantısı
            self.pg_connection = psycopg2.connect(
                host=self.pg_host,
                port=self.pg_port,
                database=self.pg_database,
                user=self.pg_user,
                password=self.pg_password
            )
            self.pg_connection.autocommit = True
            
            logger.info("Azure Storage ve PostgreSQL bağlantıları başarılı")
            
        except Exception as e:
            logger.error(f"Bağlantı hatası: {str(e)}")
            raise
            
    def get_all_images(self) -> List[Dict[str, str]]:
        """Azure Storage'dan tüm görselleri listele"""
        try:
            container_client = self.blob_service_client.get_container_client(self.container_name)
            blobs = []
            
            for blob in container_client.list_blobs():
                # Sadece resim dosyalarını al
                if blob.name.lower().endswith(('.jpg', '.jpeg', '.png', '.bmp', '.gif')):

                    # Normal URL ve SAS token'lı URL oluştur
                    blob_url = f"{container_client.url}/{quote(blob.name)}"
                    sas_url = f"https://{self.account_name}.blob.core.windows.net/{self.container_name}/{quote(blob.name)}?{self.sas_token}"
                    
                    blobs.append({
                        'name': blob.name,
                        'url': blob_url,
                        'sas_url': sas_url,
                        'folder': '/'.join(blob.name.split('/')[:-1]) if '/' in blob.name else '',
                        'size': blob.size,
                        'last_modified': blob.last_modified
                    })
                    
            logger.info(f"Toplam {len(blobs)} görsel dosyası bulundu")
            return blobs
            
        except Exception as e:
            logger.error(f"Azure Storage'dan dosya listesi alınamadı: {str(e)}")
            raise
            
    def download_image(self, blob_name: str) -> bytes:
        """Görseli Azure Storage'dan indir"""
        try:
            blob_client = self.blob_service_client.get_blob_client(
                container=self.container_name, 
                blob=blob_name
            )
            return blob_client.download_blob().readall()
            
        except Exception as e:
            logger.error(f"Görsel indirilemedi ({blob_name}): {str(e)}")
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
        """API endpoint'ine SAS URL gönder"""
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
                for idx, satir in enumerate(satirlar):
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
                        satir.get('konum', ''),
                        satir.get('ana_urun', ''),
                        satir.get('yan_urunler', ''),
                        json.dumps(data, ensure_ascii=False)
                    ))
                    
            logger.info(f"Content sonuçları kaydedildi: {len(satirlar)} satır")
            
        except Exception as e:
            logger.error(f"Content kaydetme hatası: {str(e)}")
            
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
            
            doluluk_metni = " | ".join(doluluk_ozeti)
            
            with self.pg_connection.cursor() as cursor:
                # Tek bir satır olarak kaydet (özet)
                cursor.execute("""
                    INSERT INTO analyze_stock_row (
                        source_url, reyon_id, doluluk, durum, aciliyet,
                        kasa_gorunurlugu, doluluk_seviyeleri, raw
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                """, (
                    source_url,
                    f"Toplam {ozet.get('toplam_kasa', len(reyon_durumlari))} kasa",
                    None,  # Doluluk oranı gerek yok
                    f"Dolu:{ozet.get('dolu_kasa', 0)} Normal:{ozet.get('normal_kasa', 0)} Kritik:{ozet.get('kritik_kasa', 0)} Boş:{ozet.get('boş_kasa', 0)}",
                    'orta' if ozet.get('kritik_kasa', 0) > 0 or ozet.get('boş_kasa', 0) > 0 else 'düşük',
                    True,
                    doluluk_metni,  # BASİT METİN FORMAT!
                    json.dumps(data, ensure_ascii=False)
                ))
                    
            logger.info(f"Stock sonuçları kaydedildi: {len(reyon_durumlari)} reyon (BASİT METİN)")
            logger.info(f"Doluluk özeti: {doluluk_metni}")
            
        except Exception as e:
            logger.error(f"Stock kaydetme hatası: {str(e)}")
            
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
            
            with self.pg_connection.cursor() as cursor:
                if hatalar:
                    # Her hata için ayrı satır
                    for hata in hatalar:
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
                            json.dumps(olumlu_yerlesimler, ensure_ascii=False),
                            json.dumps(genel_oneriler, ensure_ascii=False),
                            json.dumps(data, ensure_ascii=False)
                        ))
                else:
                    # Hata yoksa tek satır
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
                        json.dumps(olumlu_yerlesimler, ensure_ascii=False),
                        json.dumps(genel_oneriler, ensure_ascii=False),
                        json.dumps(data, ensure_ascii=False)
                    ))
                    
            logger.info(f"Evaluation sonuçları kaydedildi: {len(hatalar) or 1} satır")
            
        except Exception as e:
            logger.error(f"Evaluation kaydetme hatası: {str(e)}")
            
    def process_single_image_stock_only(self, blob_info: Dict) -> Dict:
        """Tek görseli işle - SADECE STOCK ANALİZİ"""
        sas_url = blob_info['sas_url']  # SAS token'lı URL'i source_url olarak kullan
        blob_name = blob_info['name']
        
        logger.info(f"Stock analizi: {blob_name}")
        logger.info(f"SAS URL: {sas_url[:100]}...")
        
        try:
            # Sadece Stock API'sini çağır
            stock_result = self.process_stock_api(sas_url, sas_url)
            
            # Sonuçları kaydet (SAS URL'i source_url olarak)
            self.save_stock_results(sas_url, stock_result)
            
            return {
                'success': True,
                'blob_name': blob_name,
                'source_url': sas_url,
                'stock_success': stock_result.get('success', False)
            }
            
        except Exception as e:
            logger.error(f"Stock analizi hatası ({blob_name}): {str(e)}")
            return {
                'success': False,
                'blob_name': blob_name,
                'source_url': sas_url,
                'error': str(e)
            }

    def process_single_image(self, blob_info: Dict) -> Dict:
        """Tek görseli işle - SAS URL ile"""
        sas_url = blob_info['sas_url']  # SAS token'lı URL'i source_url olarak kullan
        blob_name = blob_info['name']
        
        logger.info(f"İşleniyor: {blob_name}")
        logger.info(f"SAS URL source_url olarak kaydedilecek: {sas_url[:100]}...")
        
        try:
            # API'leri sırayla çağır (SAS URL ile)
            content_result = self.process_content_api(sas_url, sas_url)
            time.sleep(self.delay_between_requests)
            
            stock_result = self.process_stock_api(sas_url, sas_url)
            time.sleep(self.delay_between_requests)
            
            evaluation_result = self.process_evaluation_api(
                sas_url, sas_url, content_result
            )
            
            # Sonuçları kaydet (SAS URL'i source_url olarak)
            self.save_content_results(sas_url, content_result)
            self.save_stock_results(sas_url, stock_result)
            self.save_evaluation_results(sas_url, evaluation_result)
            
            return {
                'success': True,
                'blob_name': blob_name,
                'source_url': sas_url,
                'content_success': content_result.get('success', False),
                'stock_success': stock_result.get('success', False),
                'evaluation_success': evaluation_result.get('success', False)
            }
            
        except Exception as e:
            logger.error(f"Görsel işleme hatası ({blob_name}): {str(e)}")
            return {
                'success': False,
                'blob_name': blob_name,
                'source_url': sas_url,
                'error': str(e)
            }
            
    def run_batch_processing(self):
        """Ana batch işlem döngüsü"""
        logger.info("Batch işlemi başlatılıyor...")
        
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
        """SADECE STOCK ANALİZİ için batch işlem döngüsü"""
        logger.info("Stock-Only Batch işlemi başlatılıyor...")
        
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
            
            logger.info(f"Toplam {total_images} görsel SADECE STOCK ANALİZİ için işlenecek")
            
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
                        logger.info(f"[STOCK OK] {result['blob_name']} başarılı ({processed}/{total_images})")
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
            logger.info("STOCK-ONLY BATCH İŞLEMİ TAMAMLANDI")
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
        print("2. Sadece Stock Analizi (Hızlı)")
        
        while True:
            choice = input("\nHangi modu çalıştırmak istiyorsun? (1/2): ").strip()
            if choice == "1":
                logger.info("TAM ANALİZ modu seçildi")
                processor.run_batch_processing()
                break
            elif choice == "2":
                logger.info("SADECE STOCK ANALİZİ modu seçildi")
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