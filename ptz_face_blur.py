"""
PTZ Face Blur Service
Notebook Cell 1: Yüzlerin Blur'lanması
S3'ten snapshot'ları alır, yüzleri blur'lar ve tekrar S3'e yükler.
"""
import os
import cv2
import torch
from pathlib import Path
from datetime import datetime
from facenet_pytorch import MTCNN
import boto3
from botocore.exceptions import ClientError
from botocore.config import Config
from dotenv import load_dotenv
# urllib3 SSL uyarılarını bastır (self-signed certificate için)
import urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# .env dosyasını yükle
load_dotenv()

# AWS checksum hesaplama ve doğrulama için environment variable'ları ayarla
# Bu, bazı S3 uyumlu sistemlerde (Cohesity gibi) Content-Length sorunlarını çözebilir
os.environ.setdefault("AWS_REQUEST_CHECKSUM_CALCULATION", "when_required")
os.environ.setdefault("AWS_RESPONSE_CHECKSUM_VALIDATION", "when_required")

# === Klasörler ===
SNAPSHOTS_ROOT = Path("snapshots")  # camera_XXX/YYYY-MM-DD/HH/*.jpg

# === S3 Object Storage Ayarları ===
S3_ENDPOINT_URL = os.getenv("S3_ENDPOINT_URL", "https://161cohesity.carrefoursa.com:3000")
S3_ACCESS_KEY_ID = os.getenv("S3_ACCESS_KEY_ID", "sWxdTl3ERx7myBE1qpW06_haVvuhATcdsmBbqaWkXYU")
S3_SECRET_ACCESS_KEY = os.getenv("S3_SECRET_ACCESS_KEY", "Ti9Fonk3wYyG5PMx5LaGUmlcVyCuqsE5BLVV5vv8PU0")
S3_BUCKET_NAME = os.getenv("S3_BUCKET_NAME", "Grocery")

_s3_client = None

def _ensure_s3_client():
    """S3 client'ı başlat"""
    global _s3_client
    if not S3_ACCESS_KEY_ID or not S3_SECRET_ACCESS_KEY:
        return None
    if _s3_client is None:
        _s3_client = boto3.client(
            "s3",
            endpoint_url=S3_ENDPOINT_URL,
            aws_access_key_id=S3_ACCESS_KEY_ID,
            aws_secret_access_key=S3_SECRET_ACCESS_KEY,
            verify=False,  # self-signed için
            config=Config(
                signature_version="s3v4",
                s3={"addressing_style": "path"},  # ÖNEMLİ: path style
            ),
        )
    return _s3_client

def _upload_file(local_path: Path, s3_key: str, content_type: str = "image/jpeg"):
    """Dosyayı S3'e yükle (varsa üzerine yazar)."""
    s3 = _ensure_s3_client()
    if not s3:
        return None
    try:
        if not local_path.exists():
            print(f"⚠️  Lokal dosya bulunamadı: {local_path}")
            return None
        
        # Dosyayı okuyup bytes olarak al
        with open(local_path, "rb") as f:
            data = f.read()
        
        # put_object kullan (ContentLength otomatik hesaplanır)
        s3.put_object(
            Bucket=S3_BUCKET_NAME,
            Key=s3_key,
            Body=data,
            ContentType=content_type
        )
        return s3_key
    except Exception as e:
        print(f"⚠️  S3 upload hatası ({s3_key}): {e}")
        return None

def _download_file(s3_key: str, local_path: Path) -> bool:
    """S3'ten dosyayı indir"""
    s3 = _ensure_s3_client()
    if not s3:
        return False
    try:
        local_path.parent.mkdir(parents=True, exist_ok=True)
        s3.download_file(S3_BUCKET_NAME, s3_key, str(local_path))
        return True
    except ClientError as e:
        print(f"⚠️  S3 indirme hatası ({s3_key}): {e}")
        return False

def _list_blobs_in_path(prefix: str) -> list:
    """S3'te belirli bir prefix altındaki tüm object'leri listele"""
    s3 = _ensure_s3_client()
    if not s3:
        return []
    try:
        blobs = []
        paginator = s3.get_paginator('list_objects_v2')
        pages = paginator.paginate(Bucket=S3_BUCKET_NAME, Prefix=prefix)
        for page in pages:
            if 'Contents' in page:
                for obj in page['Contents']:
                    blobs.append(obj['Key'])
        return sorted(blobs)
    except ClientError as e:
        print(f"⚠️  S3 listeleme hatası ({prefix}): {e}")
        return []

device = 'cuda' if torch.cuda.is_available() else 'cpu'
mtcnn = MTCNN(keep_all=True, device=device)

def _to_snapshot_blob_path(local_path: Path) -> str:
    """SNAPSHOTS_ROOT'e göre bağıl yolu blob yoluna çevirir: snapshots/<...>"""
    rel = local_path.relative_to(SNAPSHOTS_ROOT)
    return f"snapshots/{rel.as_posix()}"

def blur_faces(img_path: Path):
    """Yüzleri bulanıklaştır, yerinde kaydet ve S3 Object Storage'a aynı yapıyla yükle."""
    img = cv2.imread(str(img_path))
    if img is None:
        print(f"⚠️  Görsel okunamadı: {img_path}")
        return None

    rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
    boxes, _ = mtcnn.detect(rgb)

    if boxes is not None:
        for box in boxes:
            x1, y1, x2, y2 = [int(coord) for coord in box]
            face = img[y1:y2, x1:x2]
            if face.size == 0:
                continue
            blurred = cv2.GaussianBlur(face, (51, 51), 30)
            img[y1:y2, x1:x2] = blurred

    cv2.imwrite(str(img_path), img)

    # S3'e yükle
    s3_key = _to_snapshot_blob_path(img_path)
    _upload_file(img_path, s3_key, content_type="image/jpeg")
    print(f"✔️  Blur+Upload: {img_path.name} -> {s3_key}")
    return s3_key

def process_all_cameras_snapshots():
    """S3'ten tüm kameralar için son saat klasöründeki görüntüleri indir, blur'la ve S3'e yükle."""
    import tempfile
    import shutil
    
    # Geçici klasör oluştur
    temp_dir = Path(tempfile.mkdtemp(prefix="face_blur_"))
    
    try:
        # S3'ten tüm kameraları bul
        prefix = "snapshots/camera_"
        all_blobs = _list_blobs_in_path(prefix)
        
        if not all_blobs:
            print("[!] S3'te snapshot bulunamadı")
            return
        
        # Kamera -> tarih -> saat yapısını oluştur
        camera_data = {}
        for blob_path in all_blobs:
            parts = blob_path.split("/")
            if len(parts) >= 4 and parts[1].startswith("camera_"):
                camera_id = parts[1]
                date_name = parts[2]
                hour_name = parts[3]
                filename = parts[4] if len(parts) > 4 else None
                
                if filename and filename.lower().endswith(('.jpg', '.jpeg')):
                    key = (camera_id, date_name, hour_name)
                    if key not in camera_data:
                        camera_data[key] = []
                    camera_data[key].append(blob_path)
        
        if not camera_data:
            print("[!] İşlenecek snapshot bulunamadı")
            return
        
        # Her kamera için en son tarih/saat klasörünü işle
        processed_cameras = set()
        for (camera_id, date_name, hour_name), s3_keys in camera_data.items():
            if camera_id in processed_cameras:
                continue
            
            # En son tarih/saat için sadece bir kez işle
            print(f"\n📷 Kamera: {camera_id} | 📁 {date_name}/{hour_name}")
            
            # S3'ten snapshot'ları indir
            for s3_key in s3_keys:
                filename = s3_key.split('/')[-1]
                local_path = temp_dir / camera_id / date_name / hour_name / filename
                local_path.parent.mkdir(parents=True, exist_ok=True)
                
                if _download_file(s3_key, local_path):
                    try:
                        blur_faces(local_path)
                    except Exception as e:
                        print(f"⚠️  Hata ({filename}): {e}")
            
            processed_cameras.add(camera_id)
    
    finally:
        # Geçici klasörü temizle
        if temp_dir.exists():
            shutil.rmtree(temp_dir, ignore_errors=True)
            print(f"[i] Geçici klasör temizlendi: {temp_dir}")

if __name__ == "__main__":
    print("="*60)
    print("PTZ Face Blur Service - Başlatılıyor...")
    print("="*60)
    process_all_cameras_snapshots()
    print("="*60)
    print("PTZ Face Blur Service - Tamamlandı")
    print("="*60)

