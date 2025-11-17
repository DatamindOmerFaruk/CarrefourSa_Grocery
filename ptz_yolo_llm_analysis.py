"""
PTZ YOLO + LLM Analysis Service
Notebook Cell 2: YOLO ile meyve sebze detection ve LLM ile çürük tespiti
S3'ten snapshot'ları alır, YOLO ile detection yapar, collage'lar oluşturur, 
LLM ile analiz eder ve sonuçları S3'e yükler.
"""
import os
import re
import csv
import json
import base64
import mimetypes
import tempfile
import shutil
from pathlib import Path
from typing import List, Dict, Tuple, Optional, Any
from dataclasses import dataclass
from datetime import datetime
from io import BytesIO

# ------- ENV -------
def _ensure(pkg, pipname=None):
    try: 
        return __import__(pkg)
    except Exception:
        import sys, subprocess
        subprocess.check_call([sys.executable, "-m", "pip", "install", pipname or pkg, "-q"])
        return __import__(pkg)

dotenv = _ensure("dotenv", "python-dotenv")
from dotenv import load_dotenv, find_dotenv

dotenv_path = find_dotenv(usecwd=True)
if dotenv_path:
    load_dotenv(dotenv_path, override=True)

# === S3 Object Storage Ayarları ===
try:
    import boto3
    from botocore.exceptions import ClientError
except Exception:
    import sys, subprocess
    subprocess.check_call([sys.executable, "-m", "pip", "install", "boto3>=1.34.0", "-q"])
    import boto3
    from botocore.exceptions import ClientError

# S3 Ayarları
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
            's3',
            endpoint_url=S3_ENDPOINT_URL,
            aws_access_key_id=S3_ACCESS_KEY_ID,
            aws_secret_access_key=S3_SECRET_ACCESS_KEY,
            verify=False  # Self-signed certificate için
        )
    return _s3_client

def download_blob_to_path(s3_key: str, local_path: Path) -> bool:
    """S3'ten dosyayı indir ve lokal path'e kaydet"""
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

def upload_file_to_blob(local_path: Path, s3_key: str, content_type: str = "image/jpeg") -> Optional[str]:
    """Dosyayı S3'e yükle"""
    s3 = _ensure_s3_client()
    if not s3:
        return None
    try:
        s3.upload_file(
            str(local_path),
            S3_BUCKET_NAME,
            s3_key,
            ExtraArgs={'ContentType': content_type}
        )
        return s3_key
    except ClientError as e:
        print(f"⚠️  S3 upload hatası ({local_path.name}): {e}")
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

def get_blob_url(s3_key: str) -> Optional[str]:
    """
    S3 Object Storage URL'i oluşturur.
    Format: https://161cohesity.carrefoursa.com:3000/Grocery/<s3_key>
    """
    if not s3_key:
        return None
    try:
        if S3_ENDPOINT_URL.endswith('/'):
            return f"{S3_ENDPOINT_URL}{S3_BUCKET_NAME}/{s3_key}"
        else:
            return f"{S3_ENDPOINT_URL}/{S3_BUCKET_NAME}/{s3_key}"
    except Exception as e:
        print(f"⚠️  S3 URL oluşturma hatası ({s3_key}): {e}")
        return None

def get_snapshot_blob_path_from_local(local_snapshot_path: Path, camera_id: str, date_name: str, hour_name: str) -> str:
    """
    Lokal snapshot path'inden S3 key'ini oluşturur.
    Format: snapshots/camera_XXX/YYYY-MM-DD/HH/filename.jpg
    """
    filename = local_snapshot_path.name
    return f"snapshots/{camera_id}/{date_name}/{hour_name}/{filename}"

# --- Ayarlar ---
CAMERAS_YAML = Path("multi_camera_system/cameras.yaml")
MODEL_PATH = Path("best.pt")
TEMP_DIR = Path(tempfile.mkdtemp(prefix="crops_"))

BATCH_SIZE = 25
GRID_COLS = 5
GRID_ROWS = 5
TILE_SIZE = (256, 256)
CAPTION_H = 28
PADDING = 6
FONT_SIZE = 16
FONT_PATH = os.getenv("COLLAGE_FONT", "")

MIN_CONF_ROTTEN = float(os.getenv("MIN_CONF_ROTTEN", "0.85"))
AZURE_ENDPOINT = (os.getenv("AZURE_OPENAI_ENDPOINT") or "").strip()
AZURE_API_KEY = (os.getenv("AZURE_OPENAI_API_KEY") or "").strip()
DEPLOYMENT = (os.getenv("AZURE_OPENAI_DEPLOYMENT") or "gpt-4.1").strip()

# ------- 3rd party -------
PIL = _ensure("PIL", "pillow")
from PIL import Image, ImageDraw, ImageFont

yaml_mod = _ensure("yaml", "pyyaml")
import yaml

def _ensure_openai():
    try:
        from openai import AzureOpenAI
        return AzureOpenAI
    except Exception:
        import sys, subprocess
        subprocess.check_call([sys.executable, "-m", "pip", "install", "openai>=1.30.0", "-q"])
        from openai import AzureOpenAI
        return AzureOpenAI

AzureOpenAI = _ensure_openai()

# ------- Veri tipleri -------
@dataclass
class Rec:
    path: Path
    id: str
    urun: str
    tarih: str
    saat: str
    magaza: str
    snapshot_blob_url: Optional[str] = None

# ------- Yardımcılar -------
def load_camera_config(camera_id: str) -> Dict[str, Any]:
    """cameras.yaml'dan belirli bir kameranın bilgilerini çek"""
    if not CAMERAS_YAML.exists(): 
        return {"store_name": "Bilinmeyen Mağaza"}
    with open(CAMERAS_YAML, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    cameras = data.get("cameras", {})
    camera = cameras.get(camera_id, {})
    return camera

def get_store_name(camera_id: str) -> str:
    """Kamera ID'sine göre mağaza ismini al"""
    config = load_camera_config(camera_id)
    return config.get("store_name", camera_id or "Bilinmeyen Mağaza")

DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
HOUR_RE = re.compile(r"^\d{1,2}$")

def find_latest_date_hour_for_camera_from_s3(camera_id: str) -> Optional[Tuple[str, str, List[str]]]:
    """
    S3 Object Storage'dan en son tarih/saat klasörünü bulur.
    Returns: (date_name, hour_name, s3_keys_list) veya None
    """
    prefix = f"snapshots/{camera_id}/"
    all_blobs = list_blobs_in_path(prefix)
    
    if not all_blobs:
        return None
    
    dates = set()
    hour_blobs = {}
    
    for blob_path in all_blobs:
        parts = blob_path.replace(prefix, "").split("/")
        if len(parts) >= 3 and DATE_RE.match(parts[0]) and HOUR_RE.match(parts[1]):
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

def _ensure_yolo():
    """YOLOv12 için ultralytics kütüphanesini yükle"""
    try:
        from ultralytics import YOLO
        return YOLO
    except Exception:
        import sys, subprocess
        subprocess.check_call([sys.executable, "-m", "pip", "install", "ultralytics>=8.0.0", "-q"])
        from ultralytics import YOLO
        return YOLO

def run_detection_and_crop(snapshot_paths: List[Path], output_dir: Path, 
                           model_path: Path = MODEL_PATH,
                           upload_to_s3: bool = True) -> List[Dict[str, Any]]:
    """
    YOLOv12 ile detection yapıp crop'ları kaydeder ve S3'e yükler.
    """
    YOLO = _ensure_yolo()
    if not model_path.exists():
        raise FileNotFoundError(f"Model dosyası bulunamadı: {model_path}")
    
    print(f"[i] Model yükleniyor: {model_path}")
    model = YOLO(str(model_path))
    
    all_crops = []
    for snapshot_path in snapshot_paths:
        print(f"[→] Detection: {snapshot_path.name}")
        try:
            results = model.predict(str(snapshot_path), verbose=False)
        except Exception as e:
            print(f"⚠️  Detection hatası ({snapshot_path.name}): {e}")
            continue
            
        if not results or len(results) == 0: 
            continue
        result = results[0]
        if result.boxes is None or len(result.boxes) == 0: 
            continue
        
        for idx, box in enumerate(result.boxes):
            x1, y1, x2, y2 = box.xyxy[0].cpu().numpy()
            conf = float(box.conf[0].cpu().numpy())
            cls_id = int(box.cls[0].cpu().numpy())
            class_name = result.names[cls_id] if cls_id < len(result.names) else f"class_{cls_id}"
            
            class_dir = output_dir / class_name
            class_dir.mkdir(parents=True, exist_ok=True)
            crop_filename = f"{snapshot_path.stem}_{idx:03d}_{conf:.2f}.jpg"
            crop_path = class_dir / crop_filename
            
            try:
                img = Image.open(snapshot_path)
                img_width, img_height = img.size
                x1 = max(0, int(x1))
                y1 = max(0, int(y1))
                x2 = min(img_width, int(x2))
                y2 = min(img_height, int(y2))
                
                if x2 <= x1 or y2 <= y1:
                    print(f"⚠️  Geçersiz bounding box: ({x1},{y1},{x2},{y2})")
                    continue
                    
                crop_img = img.crop((x1, y1, x2, y2))
                crop_img.save(crop_path, quality=95)
                
                if upload_to_s3:
                    temp_parts = list(crop_path.parts)
                    crops_idx = next(i for i, p in enumerate(temp_parts) if p == "crops")
                    s3_key = "/".join(temp_parts[crops_idx:])
                    upload_file_to_blob(crop_path, s3_key, content_type="image/jpeg")
                
                txt_path = crop_path.with_suffix(".txt")
                with open(txt_path, "w") as f:
                    f.write(f"{cls_id} {conf:.6f} {x1} {y1} {x2} {y2}\n")
                
                all_crops.append({
                    "crop_path": crop_path,
                    "snapshot_path": snapshot_path,
                    "class_name": class_name,
                    "class_id": cls_id,
                    "confidence": conf,
                    "bbox": [float(x1), float(y1), float(x2), float(y2)]
                })
            except Exception as e:
                print(f"⚠️  Crop işleme hatası ({snapshot_path.name}, {idx}): {e}")
                continue
    
    print(f"[✓] Toplam {len(all_crops)} crop oluşturuldu")
    return all_crops

def chunked(seq, n: int):
    for i in range(0, len(seq), n):
        yield seq[i:i+n]

try:
    RESAMPLE = Image.Resampling.LANCZOS
except Exception:
    RESAMPLE = Image.LANCZOS if hasattr(Image, "LANCZOS") else Image.ANTIALIAS

def load_font():
    try:
        if FONT_PATH and Path(FONT_PATH).exists():
            return ImageFont.truetype(FONT_PATH, FONT_SIZE)
    except Exception:
        pass
    return ImageFont.load_default()

def _text_size(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.ImageFont):
    if hasattr(draw, "textbbox"):
        x0,y0,x1,y1 = draw.textbbox((0,0), text, font=font)
        return x1-x0, y1-y0
    try:
        return font.getsize(text)
    except Exception:
        return (len(text)*8, FONT_SIZE)

def draw_caption_bar(draw, xy, text, font):
    x1,y1,x2,y2 = xy
    draw.rectangle([x1,y1,x2,y2], fill=(0,0,0))
    tw, th = _text_size(draw, text, font)
    tx = x1 + (x2-x1-tw)//2
    ty = y1 + (y2-y1-th)//2
    draw.text((tx,ty), text, fill=(255,255,255), font=font)

def make_collage(batch: List['Rec'], out_dir: Path, index: int, upload_to_s3: bool = True) -> Tuple[Path, Optional[str]]:
    """Collage oluştur ve S3'e yükle."""
    W = GRID_COLS * (TILE_SIZE[0] + 2*PADDING)
    H = GRID_ROWS * (TILE_SIZE[1] + CAPTION_H + 2*PADDING)
    canvas = Image.new("RGB", (W,H), (30,30,30))
    draw = ImageDraw.Draw(canvas)
    font = load_font()

    for i, rec in enumerate(batch):
        r = i // GRID_COLS
        c = i % GRID_COLS
        x0 = c * (TILE_SIZE[0] + 2*PADDING) + PADDING
        y0 = r * (TILE_SIZE[1] + CAPTION_H + 2*PADDING) + PADDING
        try:
            im = Image.open(rec.path).convert("RGB")
        except Exception as e:
            print(f"⚠️  Collage görüntü yüklenemedi: {rec.path} - {e}")
            im = Image.new("RGB", TILE_SIZE, (80,80,80))
        im = im.copy()
        im.thumbnail(TILE_SIZE, RESAMPLE)
        tile = Image.new("RGB", TILE_SIZE, (20,20,20))
        ox = (TILE_SIZE[0]-im.size[0])//2
        oy = (TILE_SIZE[1]-im.size[1])//2
        tile.paste(im, (ox,oy))
        canvas.paste(tile, (x0,y0))

        num = str(i+1)
        cap_y1 = y0 + TILE_SIZE[1]
        cap_y2 = cap_y1 + CAPTION_H
        draw_caption_bar(draw, (x0,cap_y1,x0+TILE_SIZE[0],cap_y2), num, font)

    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"collage_{index:03d}.jpg"
    canvas.save(out_path, quality=88, optimize=True)
    
    s3_path = None
    if upload_to_s3:
        temp_parts = list(out_path.parts)
        crops_idx = next(i for i, p in enumerate(temp_parts) if p == "crops")
        s3_key = "/".join(temp_parts[crops_idx:])
        s3_path = upload_file_to_blob(out_path, s3_key, content_type="image/jpeg")
    
    return out_path, s3_path

def guess_mime(path: Path) -> str:
    mt, _ = mimetypes.guess_type(str(path))
    return mt or "image/jpeg"

def b64_image(path: Path) -> str:
    with open(path, "rb") as f:
        return base64.b64encode(f.read()).decode("utf-8")

def prompt_rotten_only(batch_size: int, min_conf: float, num_to_class: Dict[int, str]) -> str:
    mapping = ", ".join([f"{i}={cls}" for i, cls in num_to_class.items()])
    return (
        f"Bu görsel {batch_size} kutudan oluşan tek bir kolajdır. "
        "Her kutuda 1'den başlayarak artan sıra numarası vardır. "
        f"Numara→Ürün eşleşmesi: {mapping}.\n\n"
        "Yalnızca ilgili numarada belirtilen ürün türüyle açıkça eşleşen kareleri değerlendir. "
        "Ürün türü belirgin şekilde farklıysa veya meyve/sebze dışı bir nesne baskınsa, o kareyi değerlendirme kapsamı dışında bırak. "
        "İnsan, yüz, vücut parçası, metin, silah, yaralanma vb. içerik sezersen hiçbir değerlendirme yapma.\n\n"
        "Değerlendirme: Belirgin çürükleri işaretle; küçük lekeler/olgunlaşma taze kabul. "
        f"Sadece güvenin {min_conf:.2f} ve üzerindeyse çürük olarak bildir. "
        "Çıktı formatı tek bir JSON nesnesi olmalı ve şu yapıyı içermelidir:\n"
        "{\"rotten\": [{\"id\": <1..N>, \"guven\": 0..1}]}\n"
        "Listede olmayan kareler taze kabul edilir."
    )

def _ensure_openai_client():
    return AzureOpenAI(api_key=AZURE_API_KEY, api_version="2024-06-01", azure_endpoint=AZURE_ENDPOINT)

SAFE_SYSTEM_MESSAGE = (
    "You are an assistant that evaluates produce freshness in retail photos. "
    "Analyze only non-sensitive, non-human content (fruits/vegetables in store crates). "
    "Do not discuss or infer anything about people, faces, body parts, weapons, injuries, or text content. "
    "If such content appears, return a neutral JSON with no items marked rotten."
)

def azure_classify_collage(client, deployment: str, collage_path: Path, batch_size: int,
                           num_to_class: Dict[int, str], min_conf: float, 
                           batch_records: List = None) -> Dict[str, Any]:
    """Azure OpenAI ile collage analizi."""
    b64 = b64_image(collage_path)
    user_text = prompt_rotten_only(batch_size, min_conf, num_to_class)
    base_messages = [
        {"role": "system", "content": SAFE_SYSTEM_MESSAGE},
        {"role": "user", "content": [
            {"type": "text", "text": user_text},
            {"type": "image_url", "image_url": {"url": f"data:{guess_mime(collage_path)};base64,{b64}"}}
        ]}
    ]

    def _call(messages):
        return client.chat.completions.create(
            model=deployment,
            messages=messages,
            temperature=0.0,
            max_tokens=1000,
            response_format={"type": "json_object"},
        )

    try:
        resp = _call(base_messages)
    except Exception as e1:
        try:
            safer = [
                {"role": "system", "content": SAFE_SYSTEM_MESSAGE},
                {"role": "user", "content": [
                    {"type": "text", "text": user_text},
                    {"type": "image_url", "image_url": {"url": f"data:{guess_mime(collage_path)};base64,{b64}"}}
                ]}
            ]
            resp = _call(safer)
        except Exception as e2:
            error_log = {
                "timestamp": datetime.now().isoformat(),
                "error_primary": str(e1),
                "error_secondary": str(e2),
                "collage_path": str(collage_path),
                "batch_size": batch_size
            }
            err_file = collage_path.with_suffix(".llm_error.json")
            with open(err_file, "w", encoding="utf-8") as f:
                json.dump(error_log, f, ensure_ascii=False, indent=2)
            return {"rotten": [], "error": "llm_error", "skipped": True}

    try:
        j = json.loads(resp.choices[0].message.content)
        return j if isinstance(j, dict) and "rotten" in j else {"rotten": []}
    except Exception:
        return {"rotten": []}

def gather_crops_for_hour(crops_dir: Path, magaza: str, date_name: str, hour_name: str, 
                          crop_data: List[Dict[str, Any]], camera_id: str) -> List[Rec]:
    """Crop klasöründeki tüm jpg dosyalarını Rec objesine dönüştürür."""
    exts = (".jpg",".jpeg",".png",".bmp",".webp")
    recs: List[Rec] = []
    excluded_dirs = {"collages", ".git", "__pycache__"}
    
    crop_to_snapshot = {}
    for crop_info in crop_data:
        crop_path = crop_info.get("crop_path")
        snapshot_path = crop_info.get("snapshot_path")
        if crop_path and snapshot_path:
            crop_to_snapshot[crop_path] = snapshot_path
    
    for class_dir in sorted([d for d in crops_dir.iterdir() 
                             if d.is_dir() and d.name not in excluded_dirs]):
        urun = class_dir.name
        for p in sorted(class_dir.glob("*")):
            if p.suffix.lower() in exts:
                snapshot_path = crop_to_snapshot.get(p)
                snapshot_blob_url = None
                
                if snapshot_path:
                    snapshot_s3_key = get_snapshot_blob_path_from_local(
                        snapshot_path, camera_id, date_name, hour_name
                    )
                    snapshot_blob_url = get_blob_url(snapshot_s3_key)
                
                recs.append(Rec(
                    path=p, 
                    id=p.stem, 
                    urun=urun, 
                    tarih=date_name,
                    saat=hour_name.zfill(2) + ":00:00", 
                    magaza=magaza,
                    snapshot_blob_url=snapshot_blob_url
                ))
    return recs

def write_csv(path: Path, rows: List[Dict]):
    if not rows: 
        return
    fieldnames = set()
    for r in rows: 
        fieldnames.update(r.keys())
    ordered = ["id","urun","magaza","tarih","saat","durum","guven","dosya"]
    for f in sorted(fieldnames):
        if f not in ordered: 
            ordered.append(f)
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=ordered)
        w.writeheader()
        w.writerows(rows)

def write_summary(path: Path, rows: List[Dict]):
    total = len(rows)
    rotten = sum(1 for r in rows if r.get("durum") == "çürük")
    fresh = total - rotten
    rate = (rotten / total * 100.0) if total > 0 else 0.0
    with open(path, "w", encoding="utf-8") as f:
        f.write(f"Toplam: {total}\nÇürük : {rotten}\nSağlıklı: {fresh}\nÇürük Oranı: {rate:.2f}%\n")

def main(camera_id: str = None):
    """
    Ana işlem: S3'ten snapshot'ları indirir, işler, 
    crop'lar, LLM analizi yapar ve tüm çıktıları S3'e yükler.
    """
    if not AZURE_ENDPOINT or not AZURE_API_KEY:
        raise RuntimeError("AZURE_OPENAI_ENDPOINT / AZURE_OPENAI_API_KEY eksik.")
    
    if camera_id:
        cameras_to_process = [camera_id]
    else:
        cameras_to_process = find_all_cameras_from_s3()
        if not cameras_to_process:
            print("[!] S3 Object Storage'da hiç kamera klasörü bulunamadı")
            return
    
    print(f"[i] İşlenecek kameralar: {', '.join(cameras_to_process)}")
    
    try:
        for cam_id in cameras_to_process:
            print(f"\n{'='*60}")
            print(f"[→] {cam_id} işleniyor...")
            print(f"{'='*60}")
            
            magaza = get_store_name(cam_id)
            print(f"[i] Mağaza: {magaza}")
            
            found = find_latest_date_hour_for_camera_from_s3(cam_id)
            if not found:
                print(f"[!] {cam_id} için snapshot bulunamadı.")
                continue
            
            date_name, hour_name, s3_keys = found
            print(f"[i] Son klasör: {date_name}/{hour_name}")
            print(f"[i] Toplam snapshot: {len(s3_keys)}")
            
            temp_snapshots_dir = TEMP_DIR / cam_id / date_name / hour_name
            temp_snapshots_dir.mkdir(parents=True, exist_ok=True)
            
            print(f"[→] S3'ten snapshot'lar indiriliyor...")
            snapshot_files = []
            for s3_key in s3_keys:
                if not s3_key.lower().endswith(('.jpg', '.jpeg')):
                    continue
                filename = s3_key.split('/')[-1]
                local_path = temp_snapshots_dir / filename
                if download_blob_to_path(s3_key, local_path):
                    snapshot_files.append(local_path)
            
            if not snapshot_files:
                print(f"[!] {cam_id} - Snapshot indirilemedi")
                continue
            
            snapshot_files.sort()
            print(f"[✓] {len(snapshot_files)} snapshot indirildi")
            
            crops_dir = TEMP_DIR / "crops" / cam_id / date_name / hour_name
            crops_dir.mkdir(parents=True, exist_ok=True)
            
            print(f"[→] YOLOv12 detection başlıyor...")
            crop_data = run_detection_and_crop(snapshot_files, crops_dir, MODEL_PATH, upload_to_s3=True)
            if not crop_data:
                print(f"[!] {cam_id} - Hiç tespit yapılamadı")
                continue
            
            print(f"[i] Toplam crop: {len(crop_data)}")
            
            recs = gather_crops_for_hour(crops_dir, magaza, date_name, hour_name, crop_data, cam_id)
            if not recs:
                print(f"[!] {cam_id} - Crop yok")
                continue
            
            client = _ensure_openai_client()
            collages_dir = crops_dir / "collages"
            collages_dir.mkdir(parents=True, exist_ok=True)
            
            all_items: List[Dict] = []
            batch_idx = 1
            
            for batch in chunked(recs, BATCH_SIZE):
                print(f"[→] Batch {batch_idx} işleniyor ({len(batch)} crop)...")
                collage_path, collage_s3_path = make_collage(batch, collages_dir, batch_idx, upload_to_s3=True)
                num_to_class = {i + 1: rec.urun for i, rec in enumerate(batch)}
                
                result = azure_classify_collage(
                    client, DEPLOYMENT, collage_path, len(batch), 
                    num_to_class, MIN_CONF_ROTTEN, batch
                )
                
                if result.get("skipped"):
                    print(f"⚠️  Batch {batch_idx} atlandı (LLM hatası).")
                    batch_idx += 1
                    continue
                
                rotten_pos: Dict[int, float] = {}
                for x in result.get("rotten", []) if isinstance(result, dict) else []:
                    try:
                        idx = int(x.get("id"))
                        conf = float(x.get("guven", 0.0))
                        if 1 <= idx <= len(batch) and conf >= MIN_CONF_ROTTEN:
                            rotten_pos[idx] = conf
                    except Exception:
                        pass
                
                batch_items: List[Dict] = []
                for i, rec in enumerate(batch, start=1):
                    dosya_url = rec.snapshot_blob_url or str(rec.path)
                    
                    row = {
                        "id": rec.id,
                        "urun": rec.urun,
                        "magaza": rec.magaza,
                        "tarih": rec.tarih,
                        "saat": rec.saat,
                        "dosya": dosya_url
                    }
                    if i in rotten_pos:
                        row.update({"durum": "çürük", "guven": rotten_pos[i]})
                    else:
                        row.update({"durum": "sağlıklı"})
                    batch_items.append(row)
                
                llm_dump = {
                    "collage_path": str(collage_path),
                    "collage_blob_path": collage_s3_path,
                    "batch_size": len(batch),
                    "model_name": DEPLOYMENT,
                    "prompt_version": "rotten_only_v2_safe",
                    "latency_ms": None,
                    "num_to_class": num_to_class,
                    "min_conf_rotten": MIN_CONF_ROTTEN,
                    "raw_llm": result,
                    "items": batch_items
                }
                out_llm = collage_path.with_suffix(".llm.json")
                with open(out_llm, "w", encoding="utf-8") as f:
                    json.dump(llm_dump, f, ensure_ascii=False, indent=2)
                
                temp_parts = list(out_llm.parts)
                crops_idx = next(i for i, p in enumerate(temp_parts) if p == "crops")
                s3_llm_key = "/".join(temp_parts[crops_idx:])
                upload_file_to_blob(out_llm, s3_llm_key, content_type="application/json")
                
                all_items.extend(batch_items)
                print(f"[OK] Batch {batch_idx} -> {collage_path.name} (çürük={len(rotten_pos)}/{len(batch)})")
                batch_idx += 1
            
            out_json = crops_dir / "report_all.json"
            with open(out_json, "w", encoding="utf-8") as f:
                json.dump(all_items, f, ensure_ascii=False, indent=2)
            
            out_csv = crops_dir / "report_all.csv"
            write_csv(out_csv, all_items)
            
            out_summary = crops_dir / "summary.txt"
            write_summary(out_summary, all_items)
            
            def get_s3_key(local_path: Path) -> str:
                temp_parts = list(local_path.parts)
                crops_idx = next(i for i, p in enumerate(temp_parts) if p == "crops")
                return "/".join(temp_parts[crops_idx:])
            
            s3_json_key = get_s3_key(out_json)
            upload_file_to_blob(out_json, s3_json_key, content_type="application/json")
            
            s3_csv_key = get_s3_key(out_csv)
            upload_file_to_blob(out_csv, s3_csv_key, content_type="text/csv")
            
            s3_summary_key = get_s3_key(out_summary)
            upload_file_to_blob(out_summary, s3_summary_key, content_type="text/plain")
            
            print(f"[✓] {cam_id} tamamlandı")
            print(f"    - Crop'lar: {len(crop_data)} tespit (S3'e yüklendi)")
            print(f"    - Collage'lar: {batch_idx-1} adet (S3'e yüklendi)")
            print(f"    - Raporlar: report_all.json, report_all.csv, summary.txt (S3'e yüklendi)")
        
        print(f"\n{'='*60}")
        print("[✓] Tüm kameralar işlendi!")
        print(f"[i] Geçici klasör korunuyor: {TEMP_DIR}")
        print(f"{'='*60}")
    
    finally:
        temp_snapshots_path = TEMP_DIR
        if temp_snapshots_path.exists():
            for cam_dir in temp_snapshots_path.glob("camera_*"):
                if cam_dir.is_dir():
                    print(f"[i] Geçici snapshot klasörü temizleniyor: {cam_dir}")
                    shutil.rmtree(cam_dir, ignore_errors=True)

if __name__ == "__main__":
    print("="*60)
    print("PTZ YOLO + LLM Analysis Service - Başlatılıyor...")
    print("="*60)
    main()
    print("="*60)
    print("PTZ YOLO + LLM Analysis Service - Tamamlandı")
    print("="*60)

