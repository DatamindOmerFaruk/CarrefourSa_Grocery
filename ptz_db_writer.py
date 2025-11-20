"""
PTZ Database Writer Service
LLM analiz sonuçlarını PostgreSQL veritabanına yazar
S3'ten .llm.json dosyalarını okur ve sonuçları veritabanına kaydeder.
"""
import os
import json
import psycopg2
from pathlib import Path
from datetime import datetime, date, time
from typing import List, Dict, Optional, Any
from dotenv import load_dotenv
from botocore.exceptions import ClientError

# .env dosyasını yükle
load_dotenv()

# AWS checksum hesaplama ve doğrulama için environment variable'ları ayarla
# Bu, bazı S3 uyumlu sistemlerde (Cohesity gibi) Content-Length sorunlarını çözebilir
os.environ.setdefault("AWS_REQUEST_CHECKSUM_CALCULATION", "when_required")
os.environ.setdefault("AWS_RESPONSE_CHECKSUM_VALIDATION", "when_required")

# === S3 Object Storage Ayarları ===
try:
    import boto3
    from botocore.config import Config
    # urllib3 SSL uyarılarını bastır (self-signed certificate için)
    import urllib3
    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
except Exception:
    import sys, subprocess
    subprocess.check_call([sys.executable, "-m", "pip", "install", "boto3>=1.34.0", "-q"])
    import boto3
    from botocore.config import Config
    import urllib3
    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

S3_ENDPOINT_URL = os.getenv("S3_ENDPOINT_URL", "https://161cohesity.carrefoursa.com:3000")
S3_ACCESS_KEY_ID = os.getenv("S3_ACCESS_KEY_ID", "sWxdTl3ERx7myBE1qpW06_haVvuhATcdsmBbqaWkXYU")
S3_SECRET_ACCESS_KEY = os.getenv("S3_SECRET_ACCESS_KEY", "Ti9Fonk3wYyG5PMx5LaGUmlcVyCuqsE5BLVV5vv8PU0")
S3_BUCKET_NAME = os.getenv("S3_BUCKET_NAME", "Grocery")

_s3_client = None

def _ensure_s3_client():
    """S3 client'ı başlat"""
    global _s3_client
    if not S3_ACCESS_KEY_ID or not S3_SECRET_ACCESS_KEY:
        print("[!] S3_ACCESS_KEY_ID veya S3_SECRET_ACCESS_KEY tanımlı değil!")
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

def download_blob_to_bytes(s3_key: str) -> Optional[bytes]:
    """S3'ten dosyayı indir ve bytes olarak döndür"""
    s3 = _ensure_s3_client()
    if not s3:
        return None
    try:
        response = s3.get_object(Bucket=S3_BUCKET_NAME, Key=s3_key)
        return response['Body'].read()
    except ClientError as e:
        print(f"⚠️  S3 indirme hatası ({s3_key}): {e}")
        return None

def list_blobs_in_path(prefix: str) -> List[str]:
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

# === PostgreSQL Ayarları ===
PG_DSN = os.getenv(
    "PG_DSN",
    "postgresql://grocerryadmin:a08Iyr95vLHTYY@45.84.18.76:5432/postgres"  # Veritabanı: postgres, Kullanıcı: grocerryadmin
)

if not PG_DSN:
    print("[UYARI] PG_DSN ortam değişkeni tanımlı değil!")
    print("Örnek: postgresql://USER:PASS@HOST:5432/DB?sslmode=prefer")
    print("Veritabanı işlemleri için .env dosyasına PG_DSN ekleyin.")

# SSL mode: prefer (SSL varsa kullanır, yoksa kullanmaz)
# Sunucu SSL desteklemiyorsa otomatik olarak SSL olmadan bağlanır
if PG_DSN and "sslmode=" not in PG_DSN:
    PG_DSN += ("&" if "?" in PG_DSN else "?") + "sslmode=prefer"

# === Veritabanı Tabloları ===
DDL = """
CREATE TABLE IF NOT EXISTS llm_runs (
  id              BIGSERIAL PRIMARY KEY,
  created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  run_date        DATE NOT NULL,
  run_hour        TIME NOT NULL,
  magaza          TEXT,
  total_collages  INT,
  total_items     INT,
  rotten_count    INT NOT NULL,
  fresh_count     INT NOT NULL,
  unknown_count   INT NOT NULL,
  model_name      TEXT,
  prompt_version  TEXT,
  min_conf_rotten REAL,
  collages_json   JSONB
);
CREATE INDEX IF NOT EXISTS idx_llm_runs_created_at ON llm_runs(created_at);
CREATE INDEX IF NOT EXISTS idx_llm_runs_run_date ON llm_runs(run_date);

CREATE TABLE IF NOT EXISTS llm_items (
  id           BIGSERIAL PRIMARY KEY,
  run_id       BIGINT REFERENCES llm_runs(id) ON DELETE CASCADE,
  item_id      TEXT,
  urun         TEXT NOT NULL,
  magaza       TEXT,
  tarih        DATE NOT NULL,
  saat         TIME NOT NULL,
  durum        TEXT NOT NULL,
  dosya        TEXT,
  raw_json     JSONB,
  inserted_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_llm_items_tarih ON llm_items(tarih);
CREATE INDEX IF NOT EXISTS idx_llm_items_durum ON llm_items(durum);
CREATE INDEX IF NOT EXISTS idx_llm_items_run_id ON llm_items(run_id);
CREATE INDEX IF NOT EXISTS idx_llm_items_urun ON llm_items(urun);
"""

def ensure_tables():
    """Veritabanında gerekli tabloları oluşturur"""
    if not PG_DSN:
        raise RuntimeError("PG_DSN tanımlı değil. Veritabanı bağlantısı kurulamıyor.")
    
    try:
        with psycopg2.connect(PG_DSN) as conn:
            with conn.cursor() as cur: 
                cur.execute(DDL)
            conn.commit()
        print("[OK] Veritabanı tabloları hazır (llm_runs, llm_items)")
    except Exception as e:
        print(f"[HATA] Veritabanı bağlantısı başarısız: {e}")
        raise

def find_all_cameras_from_s3() -> List[str]:
    """S3 Object Storage'dan tüm camera_XXX klasörlerini bulur"""
    prefix = "snapshots/camera_"
    all_blobs = list_blobs_in_path(prefix)
    
    cameras = set()
    for blob_path in all_blobs:
        parts = blob_path.split("/")
        if len(parts) >= 2 and parts[1].startswith("camera_"):
            cameras.add(parts[1])
    
    return sorted(list(cameras))

def find_latest_date_hour_for_camera_from_s3(camera_id: str) -> Optional[tuple]:
    """
    S3 Object Storage'dan en son tarih/saat klasörünü bulur.
    Returns: (date_name, hour_name) veya None
    """
    import re
    DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
    HOUR_RE = re.compile(r"^\d{1,2}$")
    
    prefix = f"crops/{camera_id}/"
    all_blobs = list_blobs_in_path(prefix)
    
    if not all_blobs:
        return None
    
    dates = set()
    hour_blobs = {}
    
    for blob_path in all_blobs:
        parts = blob_path.replace(prefix, "").split("/")
        if len(parts) >= 2 and DATE_RE.match(parts[0]) and HOUR_RE.match(parts[1]):
            date_name = parts[0]
            hour_name = parts[1]
            dates.add(date_name)
            key = (date_name, hour_name)
            if key not in hour_blobs:
                hour_blobs[key] = []
            hour_blobs[key].append(blob_path)
    
    if not dates:
        return None
    
    sorted_dates = sorted(dates)
    last_date = sorted_dates[-1]
    
    last_hour_blobs = {k: v for k, v in hour_blobs.items() if k[0] == last_date}
    if not last_hour_blobs:
        return None
    
    def get_hour_num(key):
        try:
            return int(key[1])
        except:
            return -1
    
    sorted_hours = sorted(last_hour_blobs.keys(), key=get_hour_num)
    last_hour_key = sorted_hours[-1]
    
    return last_hour_key[0], last_hour_key[1], hour_blobs[last_hour_key]

def ingest_hour_directory_from_s3(camera_id: str, date_name: str, hour_name: str) -> Dict[str, Any]:
    """
    S3'ten belirli bir saat klasöründeki tüm .llm.json dosyalarını okur ve işler.
    """
    prefix = f"crops/{camera_id}/{date_name}/{hour_name}/collages/"
    all_blobs = list_blobs_in_path(prefix)
    
    llm_json_keys = [k for k in all_blobs if k.endswith(".llm.json")]
    
    if not llm_json_keys:
        print(f"[!] {camera_id}/{date_name}/{hour_name} için .llm.json dosyası bulunamadı")
        return None
    
    print(f"[i] {len(llm_json_keys)} adet .llm.json dosyası bulundu")
    
    all_items: List[Dict] = []
    collages_data: List[Dict] = []
    
    for llm_key in llm_json_keys:
        print(f"[→] Okunuyor: {llm_key}")
        data_bytes = download_blob_to_bytes(llm_key)
        if not data_bytes:
            print(f"[!] {llm_key} indirilemedi")
            continue
        
        try:
            llm_data = json.loads(data_bytes.decode('utf-8'))
        except Exception as e:
            print(f"[!] {llm_key} JSON parse hatası: {e}")
            continue
        
        items = llm_data.get("items", [])
        if not items:
            print(f"[!] {llm_key} içinde 'items' bulunamadı")
            continue
        
        all_items.extend(items)
        
        collage_info = {
            "collage_path": llm_data.get("collage_path"),
            "collage_blob_path": llm_data.get("collage_blob_path"),
            "batch_size": llm_data.get("batch_size", len(items)),
            "model_name": llm_data.get("model_name"),
            "prompt_version": llm_data.get("prompt_version"),
            "min_conf_rotten": llm_data.get("min_conf_rotten"),
            "raw_llm": llm_data.get("raw_llm", {})
        }
        collages_data.append(collage_info)
    
    if not all_items:
        print(f"[!] {camera_id}/{date_name}/{hour_name} için hiç item bulunamadı")
        return None
    
    # İstatistikler
    total_items = len(all_items)
    rotten_count = sum(1 for item in all_items if item.get("durum") == "çürük")
    fresh_count = sum(1 for item in all_items if item.get("durum") == "sağlıklı")
    unknown_count = total_items - rotten_count - fresh_count
    
    return {
        "camera_id": camera_id,
        "date_name": date_name,
        "hour_name": hour_name,
        "total_collages": len(collages_data),
        "total_items": total_items,
        "rotten_count": rotten_count,
        "fresh_count": fresh_count,
        "unknown_count": unknown_count,
        "items": all_items,
        "collages": collages_data,
        "model_name": collages_data[0].get("model_name") if collages_data else None,
        "prompt_version": collages_data[0].get("prompt_version") if collages_data else None,
        "min_conf_rotten": collages_data[0].get("min_conf_rotten") if collages_data else None
    }

def load_camera_config(camera_id: str) -> Dict[str, Any]:
    """cameras.yaml'dan belirli bir kameranın bilgilerini çek"""
    try:
        import yaml
        cameras_yaml = Path("multi_camera_system/cameras.yaml")
        if not cameras_yaml.exists(): 
            return {"store_name": "Bilinmeyen Mağaza"}
        with open(cameras_yaml, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
        cameras = data.get("cameras", {})
        camera = cameras.get(camera_id, {})
        return camera
    except Exception:
        return {"store_name": "Bilinmeyen Mağaza"}

def get_store_name(camera_id: str) -> str:
    """Kamera ID'sine göre mağaza ismini al"""
    config = load_camera_config(camera_id)
    return config.get("store_name", camera_id or "Bilinmeyen Mağaza")

def write_to_db(hour_data: Dict[str, Any]):
    """LLM analiz sonuçlarını veritabanına yazar"""
    if not PG_DSN:
        raise RuntimeError("PG_DSN tanımlı değil. Veritabanı bağlantısı kurulamıyor.")
    
    if not hour_data:
        print("[!] Yazılacak veri yok")
        return
    
    camera_id = hour_data.get("camera_id")
    date_name = hour_data.get("date_name")
    hour_name = hour_data.get("hour_name")
    magaza = get_store_name(camera_id)
    
    try:
        run_date = date.fromisoformat(date_name)
        hour_int = int(hour_name)
        run_hour = time(hour=hour_int, minute=0, second=0)
    except Exception as e:
        print(f"[!] Tarih/saat parse hatası: {e}")
        return
    
    try:
        with psycopg2.connect(PG_DSN) as conn:
            with conn.cursor() as cur:
                # llm_runs tablosuna kayıt ekle
                insert_run = """
                INSERT INTO llm_runs (
                    run_date, run_hour, magaza, total_collages, total_items,
                    rotten_count, fresh_count, unknown_count,
                    model_name, prompt_version, min_conf_rotten, collages_json
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING id
                """
                
                collages_json = json.dumps(hour_data.get("collages", []), ensure_ascii=False)
                
                cur.execute(insert_run, (
                    run_date,
                    run_hour,
                    magaza,
                    hour_data.get("total_collages", 0),
                    hour_data.get("total_items", 0),
                    hour_data.get("rotten_count", 0),
                    hour_data.get("fresh_count", 0),
                    hour_data.get("unknown_count", 0),
                    hour_data.get("model_name"),
                    hour_data.get("prompt_version"),
                    hour_data.get("min_conf_rotten"),
                    collages_json
                ))
                
                run_id = cur.fetchone()[0]
                print(f"[OK] llm_runs tablosuna kayıt eklendi: run_id={run_id}")
                
                # llm_items tablosuna kayıtları ekle
                items = hour_data.get("items", [])
                if items:
                    insert_item = """
                    INSERT INTO llm_items (
                        run_id, item_id, urun, magaza, tarih, saat, durum, dosya, raw_json
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                    """
                    
                    for item in items:
                        try:
                            item_tarih = date.fromisoformat(item.get("tarih", date_name))
                            item_saat_str = item.get("saat", f"{hour_name.zfill(2)}:00:00")
                            item_saat_parts = item_saat_str.split(":")
                            item_saat = time(
                                hour=int(item_saat_parts[0]),
                                minute=int(item_saat_parts[1]) if len(item_saat_parts) > 1 else 0,
                                second=int(item_saat_parts[2]) if len(item_saat_parts) > 2 else 0
                            )
                        except Exception as e:
                            print(f"[!] Item tarih/saat parse hatası: {e}, item={item.get('id')}")
                            item_tarih = run_date
                            item_saat = run_hour
                        
                        cur.execute(insert_item, (
                            run_id,
                            item.get("id"),
                            item.get("urun"),
                            magaza,
                            item_tarih,
                            item_saat,
                            item.get("durum"),
                            item.get("dosya"),
                            json.dumps(item, ensure_ascii=False)
                        ))
                    
                    print(f"[OK] {len(items)} adet item llm_items tablosuna eklendi")
                
                conn.commit()
                print(f"[✓] Veritabanı yazma tamamlandı: {camera_id}/{date_name}/{hour_name}")
    
    except Exception as e:
        print(f"[HATA] Veritabanı yazma hatası: {e}")
        raise

def main(camera_id: str = None):
    """
    Ana işlem: S3'ten .llm.json dosyalarını okur ve veritabanına yazar.
    """
    ensure_tables()
    
    if camera_id:
        cameras_to_process = [camera_id]
    else:
        cameras_to_process = find_all_cameras_from_s3()
        if not cameras_to_process:
            print("[!] S3 Object Storage'da hiç kamera klasörü bulunamadı")
            print("[i] Bu normal olabilir - henüz görüntü çekilmemiş veya işlenmemiş olabilir.")
            print("[i] Camera Snapshot System ve PTZ YOLO+LLM Analysis'in çalıştığından emin olun.")
            return
    
    print(f"[i] İşlenecek kameralar: {', '.join(cameras_to_process)}")
    
    for cam_id in cameras_to_process:
        print(f"\n{'='*60}")
        print(f"[→] {cam_id} işleniyor...")
        print(f"{'='*60}")
        
        found = find_latest_date_hour_for_camera_from_s3(cam_id)
        if not found:
            print(f"[!] {cam_id} için crop klasörü bulunamadı.")
            continue
        
        date_name, hour_name, _ = found
        print(f"[i] Son klasör: {date_name}/{hour_name}")
        
        hour_data = ingest_hour_directory_from_s3(cam_id, date_name, hour_name)
        if not hour_data:
            print(f"[!] {cam_id} - Veri işlenemedi")
            continue
        
        print(f"[i] Bulunan veriler:")
        print(f"    - Collage'lar: {hour_data.get('total_collages', 0)}")
        print(f"    - Toplam item: {hour_data.get('total_items', 0)}")
        print(f"    - Çürük: {hour_data.get('rotten_count', 0)}")
        print(f"    - Sağlıklı: {hour_data.get('fresh_count', 0)}")
        print(f"    - Bilinmeyen: {hour_data.get('unknown_count', 0)}")
        
        try:
            write_to_db(hour_data)
        except Exception as e:
            print(f"[HATA] {cam_id} - Veritabanı yazma hatası: {e}")
            continue
    
    print(f"\n{'='*60}")
    print("[✓] Tüm kameralar işlendi!")
    print(f"{'='*60}")

if __name__ == "__main__":
    print("="*60)
    print("PTZ Database Writer Service - Başlatılıyor...")
    print("="*60)
    main()
    print("="*60)
    print("PTZ Database Writer Service - Tamamlandı")
    print("="*60)

