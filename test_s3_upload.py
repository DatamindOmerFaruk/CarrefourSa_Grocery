"""
S3 Object Storage bağlantısını ve yükleme işlemini test eder
"""
import os
from pathlib import Path
from dotenv import load_dotenv

# .env dosyasını yükle
load_dotenv()

# S3 Ayarları
S3_ENDPOINT_URL = os.getenv("S3_ENDPOINT_URL", "https://161cohesity.carrefoursa.com:3000")
S3_ACCESS_KEY_ID = os.getenv("S3_ACCESS_KEY_ID", "")
S3_SECRET_ACCESS_KEY = os.getenv("S3_SECRET_ACCESS_KEY", "")
S3_BUCKET_NAME = os.getenv("S3_BUCKET_NAME", "Grocery")

print("="*60)
print("S3 Object Storage Test")
print("="*60)
print(f"Endpoint: {S3_ENDPOINT_URL}")
print(f"Bucket: {S3_BUCKET_NAME}")
print(f"Access Key ID: {'Tanımlı' if S3_ACCESS_KEY_ID else 'TANIMSIZ'}")
print(f"Secret Access Key: {'Tanımlı' if S3_SECRET_ACCESS_KEY else 'TANIMSIZ'}")
print("="*60)

# boto3 import
try:
    import boto3
    from botocore.exceptions import ClientError
    import urllib3
    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
    print("[OK] boto3 kütüphanesi yüklü")
except ImportError as e:
    print(f"[HATA] boto3 kütüphanesi yüklü değil: {e}")
    exit(1)

# S3 Client oluştur
if not S3_ACCESS_KEY_ID or not S3_SECRET_ACCESS_KEY:
    print("[HATA] S3 credentials tanımlı değil!")
    print("[ÇÖZÜM] .env dosyasına şunları ekleyin:")
    print("S3_ACCESS_KEY_ID=sWxdTl3ERx7myBE1qpW06_haVvuhATcdsmBbqaWkXYU")
    print("S3_SECRET_ACCESS_KEY=Ti9Fonk3wYyG5PMx5LaGUmlcVyCuqsE5BLVV5vv8PU0")
    exit(1)

try:
    s3_client = boto3.client(
        's3',
        endpoint_url=S3_ENDPOINT_URL,
        aws_access_key_id=S3_ACCESS_KEY_ID,
        aws_secret_access_key=S3_SECRET_ACCESS_KEY,
        verify=False
    )
    print("[OK] S3 client oluşturuldu")
except Exception as e:
    print(f"[HATA] S3 client oluşturulamadı: {e}")
    exit(1)

# Bucket'ı listele
print("\n[TEST 1] Bucket listesi kontrol ediliyor...")
try:
    response = s3_client.list_buckets()
    buckets = [b['Name'] for b in response.get('Buckets', [])]
    print(f"[OK] Bulunan bucket'lar: {buckets}")
    if S3_BUCKET_NAME not in buckets:
        print(f"[UYARI] '{S3_BUCKET_NAME}' bucket'ı bulunamadı!")
    else:
        print(f"[OK] '{S3_BUCKET_NAME}' bucket'ı mevcut")
except Exception as e:
    print(f"[HATA] Bucket listesi alınamadı: {e}")

# Bucket içeriğini listele
print(f"\n[TEST 2] '{S3_BUCKET_NAME}' bucket içeriği listeleniyor...")
try:
    response = s3_client.list_objects_v2(Bucket=S3_BUCKET_NAME, MaxKeys=10)
    if 'Contents' in response:
        print(f"[OK] Bucket'ta {len(response['Contents'])} object bulundu (ilk 10):")
        for obj in response['Contents'][:10]:
            print(f"  - {obj['Key']} ({obj['Size']} bytes)")
    else:
        print("[UYARI] Bucket boş veya erişim hatası")
except Exception as e:
    print(f"[HATA] Bucket içeriği listelenemedi: {e}")

# snapshots prefix'ini kontrol et
print(f"\n[TEST 3] 'snapshots/' prefix'i kontrol ediliyor...")
try:
    response = s3_client.list_objects_v2(Bucket=S3_BUCKET_NAME, Prefix="snapshots/", MaxKeys=10)
    if 'Contents' in response:
        print(f"[OK] 'snapshots/' altında {len(response['Contents'])} object bulundu (ilk 10):")
        for obj in response['Contents'][:10]:
            print(f"  - {obj['Key']} ({obj['Size']} bytes)")
    else:
        print("[UYARI] 'snapshots/' prefix'i altında object bulunamadı")
except Exception as e:
    print(f"[HATA] 'snapshots/' prefix'i kontrol edilemedi: {e}")

# Test dosyası yükle
print(f"\n[TEST 4] Test dosyası yükleniyor...")
test_file = Path("test_s3_upload.txt")
try:
    # Test dosyası oluştur
    test_file.write_text("S3 upload test - " + str(os.getpid()))
    test_key = "snapshots/test/test_upload.txt"
    
    s3_client.upload_file(
        str(test_file),
        S3_BUCKET_NAME,
        test_key,
        ExtraArgs={'ContentType': 'text/plain'}
    )
    print(f"[OK] Test dosyası yüklendi: {test_key}")
    
    # Yüklenen dosyayı kontrol et
    response = s3_client.head_object(Bucket=S3_BUCKET_NAME, Key=test_key)
    print(f"[OK] Yüklenen dosya doğrulandı: {response['ContentLength']} bytes")
    
    # Test dosyasını sil
    s3_client.delete_object(Bucket=S3_BUCKET_NAME, Key=test_key)
    print(f"[OK] Test dosyası silindi")
    test_file.unlink()
    
except Exception as e:
    print(f"[HATA] Test dosyası yüklenemedi: {e}")
    import traceback
    print(f"[DEBUG] Traceback: {traceback.format_exc()}")
    if test_file.exists():
        test_file.unlink()

print("\n" + "="*60)
print("Test tamamlandı")
print("="*60)

