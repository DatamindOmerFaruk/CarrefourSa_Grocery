#!/usr/bin/env python3
"""
Multi-Camera Snapshot System
Tüm kameralardan PTZ hedeflerine göre snapshot alır
Redis/Celery bağımlılığı olmadan çalışır
"""

import os
import time
import requests
from requests.auth import HTTPDigestAuth
from pathlib import Path
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional, Tuple
import yaml
from PIL import Image
import numpy as np
from ultralytics import YOLO
from dotenv import load_dotenv
from botocore.config import Config

# .env dosyasını yükle
load_dotenv()

# Türkiye saati (UTC+3) için timezone
TURKEY_TZ = timezone(timedelta(hours=3))

def get_turkey_time():
    """Türkiye saatini döndürür (UTC+3) - Sistem saati yanlış olsa bile doğru saati kullanır"""
    utc_now = datetime.now(timezone.utc)
    return utc_now.astimezone(TURKEY_TZ)

# S3 Object Storage için
try:
    import boto3
    from botocore.exceptions import ClientError
    # urllib3 SSL uyarılarını bastır (self-signed certificate için)
    import urllib3
    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
except ImportError:
    boto3 = None
    ClientError = None


# ============================================================================
# S3 OBJECT STORAGE ENTEGRASYONU
# ============================================================================

# S3 Ayarları (environment variables'dan alınır)
S3_ENDPOINT_URL = os.getenv("S3_ENDPOINT_URL", "https://161cohesity.carrefoursa.com:3000")
S3_ACCESS_KEY_ID = os.getenv("S3_ACCESS_KEY_ID", "")
S3_SECRET_ACCESS_KEY = os.getenv("S3_SECRET_ACCESS_KEY", "")
S3_BUCKET_NAME = os.getenv("S3_BUCKET_NAME", "Grocery")

_s3_client = None

def _ensure_s3_client():
    """S3 client'ı başlat"""
    global _s3_client
    if boto3 is None:
        print("[HATA] boto3 kütüphanesi yüklü değil!")
        return None
    if not S3_ACCESS_KEY_ID or not S3_SECRET_ACCESS_KEY:
        print("[HATA] S3_ACCESS_KEY_ID veya S3_SECRET_ACCESS_KEY tanımlı değil!")
        print(f"[DEBUG] S3_ACCESS_KEY_ID: {'Tanımlı' if S3_ACCESS_KEY_ID else 'TANIMSIZ'}")
        print(f"[DEBUG] S3_SECRET_ACCESS_KEY: {'Tanımlı' if S3_SECRET_ACCESS_KEY else 'TANIMSIZ'}")
        print("[DEBUG] .env dosyasında S3_ACCESS_KEY_ID ve S3_SECRET_ACCESS_KEY değerlerini kontrol edin.")
        return None

    if _s3_client is None:
        try:
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
            print(f"[DEBUG] S3 client oluşturuldu: endpoint={S3_ENDPOINT_URL}, bucket={S3_BUCKET_NAME}")
        except Exception as e:
            print(f"[HATA] S3 client oluşturulamadı: {e}")
            return None
    return _s3_client

def _upload_file_to_s3(local_path: Path, s3_key: str, content_type: str = "image/jpeg") -> Optional[str]:
    """Dosyayı S3'e yükle (varsa üzerine yazar)."""
    s3 = _ensure_s3_client()
    if not s3:
        print(f"[HATA] S3 client mevcut değil, yükleme yapılamıyor: {s3_key}")
        return None

    try:
        if not local_path.exists():
            print(f"[HATA] Lokal dosya bulunamadı: {local_path}")
            return None

        file_size = local_path.stat().st_size
        print(
            f"[DEBUG] S3'e yükleniyor: bucket={S3_BUCKET_NAME}, key={s3_key}, "
            f"file={local_path.name} ({file_size} bytes)"
        )

        # Dosyayı stream ederek gönder, ContentLength’i elle set et
        with open(local_path, "rb") as f:
            s3.put_object(
                Bucket=S3_BUCKET_NAME,
                Key=s3_key,
                Body=f,
                ContentType=content_type,
                ContentLength=file_size,
            )

        print(f"[DEBUG] S3'e başarıyla yüklendi: {s3_key}")
        return s3_key

    except Exception as e:
        print(f"[HATA] S3 upload hatası ({s3_key}): {e}")
        import traceback
        print(f"[DEBUG] Traceback: {traceback.format_exc()}")
        return None


def _to_snapshot_s3_key(local_path: Path, snapshots_root: Path) -> str:
    """
    Lokal snapshot path'ini S3 key'ine çevirir.
    Format: snapshots/camera_XXX/YYYY-MM-DD/HH/filename.jpg
    """
    try:
        # snapshots_root'a göre bağıl yolu al
        rel_path = local_path.relative_to(snapshots_root)
        # S3 key formatı: snapshots/camera_XXX/YYYY-MM-DD/HH/filename.jpg
        s3_key = f"snapshots/{rel_path.as_posix()}"
        return s3_key
    except ValueError:
        # Eğer path relative değilse, direkt path'i kullan
        # snapshots/camera_XXX/... formatında olmalı
        parts = local_path.parts
        if 'snapshots' in parts:
            idx = parts.index('snapshots')
            s3_key = '/'.join(parts[idx:])
            return s3_key
        # Fallback: direkt dosya adını snapshots altına koy (ideal değil ama çalışır)
        return f"snapshots/{local_path.name}"


# ============================================================================
# KAMERA KONFIGÜRASYON SINIFLARI
# ============================================================================

class CameraConfig:
    """Kamera konfigürasyon sınıfı"""
    def __init__(self, camera_id: str, config: Dict):
        self.camera_id = camera_id
        self.name = config.get('name', f'Camera {camera_id}')
        self.host = config.get('host')
        self.username = config.get('username')
        self.password = config.get('password')
        self.ptz_channel = config.get('ptz_channel', 1)
        self.stream_channel = config.get('stream_channel', 101)
        self.store_name = config.get('store_name', 'Unknown Store')
        self.move_settle_seconds = config.get('move_settle_seconds', 5)
        self.azimuth_scale = config.get('azimuth_scale', 10)
        self.elevation_scale = config.get('elevation_scale', 10)
        self.zoom_scale = config.get('zoom_scale', 10)
        raw_targets = config.get('ptz_targets')
        self.ptz_targets = raw_targets if isinstance(raw_targets, dict) else {}
        
        # Base URL
        self.base_url = f"http://{self.host}/ISAPI"
        self.auth = HTTPDigestAuth(self.username, self.password)
        
        # Session
        self.session = requests.Session()
        self.session.auth = self.auth


class CameraController:
    """Kamera kontrol sınıfı - PTZ ve snapshot işlemleri"""
    
    def __init__(self, config: CameraConfig):
        self.config = config
        self.session = config.session
        self.base_url = config.base_url
        
    def _is_ok(self, resp: requests.Response) -> bool:
        """HTTP response başarılı mı kontrol et"""
        return 200 <= resp.status_code < 300
    
    def ptz_move_absolute(self, azimuth: float, elevation: float, zoom: float, 
                         timeout_s: float = 5.0) -> bool:
        """PTZ'yi mutlak konuma taşı"""
        url = f"{self.base_url}/PTZCtrl/channels/{self.config.ptz_channel}/Absolute"
        xml_body = f"""<?xml version="1.0" encoding="UTF-8"?>
<PTZData>
  <AbsoluteHigh>
    <azimuth>{azimuth * self.config.azimuth_scale}</azimuth>
    <elevation>{elevation * self.config.elevation_scale}</elevation>
    <absoluteZoom>{zoom * self.config.zoom_scale}</absoluteZoom>
  </AbsoluteHigh>
</PTZData>"""

        try:
            resp = self.session.put(
                url, data=xml_body, auth=self.config.auth,
                headers={"Content-Type": "application/xml"},
                timeout=timeout_s
            )
            if not self._is_ok(resp):
                raise RuntimeError(f"PTZ Absolute hata: {resp.status_code} - {resp.text[:200]}")
            return True
        except requests.RequestException as e:
            raise RuntimeError(f"PTZ isteği başarısız: {e}") from e
    
    def move_ptz(self, azimuth: float, elevation: float, zoom: float) -> bool:
        """PTZ hareket fonksiyonu - ptz_move_absolute için alias"""
        return self.ptz_move_absolute(azimuth, elevation, zoom)
    
    def take_snapshot(self, target_name: str, save_dir: Path, snapshots_root: Optional[Path] = None) -> Optional[Path]:
        """
        Snapshot al, kaydet ve S3'e yükle
        
        Args:
            target_name: Hedef adı (dosya adı prefix'i)
            save_dir: Kayıt dizini (snapshots_root / camera_id)
            snapshots_root: Snapshots kök dizini (S3 key oluşturmak için, opsiyonel)
        """
        url = f"{self.base_url}/Streaming/channels/{self.config.stream_channel}/picture"
        
        try:
            resp = self.session.get(url, auth=self.config.auth, stream=True, timeout=10)
            if not self._is_ok(resp):
                raise RuntimeError(f"Snapshot hata: {resp.status_code} - {resp.text[:200]}")

            # Türkiye saati (UTC+3) kullan
            # Sistem saati yanlış olsa bile doğru saati kullanır
            now = get_turkey_time()
            
            ts_date = now.strftime("%Y-%m-%d")
            ts_hour = now.strftime("%H")
            ts_time = now.strftime("%H%M%S")

            # Kamera ID'si ile klasör yapısı: snapshots/camera_001/2025-10-19/21/
            camera_dir = save_dir
            day_dir = camera_dir / ts_date
            hour_dir = day_dir / ts_hour
            hour_dir.mkdir(parents=True, exist_ok=True)

            fname = f"{target_name}_{ts_time}.jpg"
            fpath = hour_dir / fname

            with open(fpath, "wb") as f:
                for chunk in resp.iter_content(8192):
                    if chunk:
                        f.write(chunk)

            # Dosya bütünlük kontrolü
            if fpath.stat().st_size < 5_000:  # 5 KB altı boş/bozuk olabilir
                print(f"[UYARI] {self.config.camera_id} - Snapshot dosyası çok küçük: {fpath}")
                return None

            print(f"[✓] {self.config.camera_id} - Kaydedildi: {fpath}")
            
            return fpath

        except requests.RequestException as e:
            raise RuntimeError(f"Snapshot isteği başarısız: {e}") from e
    
    def capture_snapshot(self, save_dir: Path, filename_prefix: str, snapshots_root: Optional[Path] = None) -> Optional[Path]:
        """Snapshot yakalama fonksiyonu - take_snapshot için alias"""
        return self.take_snapshot(filename_prefix, save_dir, snapshots_root)


# ============================================================================
# KONFIGÜRASYON YÜKLEME FONKSİYONLARI
# ============================================================================

def load_camera_configs(config_path: str) -> Dict[str, CameraConfig]:
    """YAML dosyasından kamera konfigürasyonlarını yükle"""
    # Eğer relative path ise, script dizinine göre ayarla
    if not os.path.isabs(config_path):
        script_dir = Path(__file__).parent
        config_path = str(script_dir / config_path)
    
    if not os.path.exists(config_path):
        raise FileNotFoundError(f"Konfigürasyon dosyası bulunamadı: {config_path}")
    
    with open(config_path, 'r', encoding='utf-8') as f:
        data = yaml.safe_load(f)
    
    cameras = {}
    for camera_id, config in data.get('cameras', {}).items():
        cameras[camera_id] = CameraConfig(camera_id, config)
    
    return cameras


def get_global_settings(config_path: str) -> Dict:
    """Global ayarları yükle"""
    # Eğer relative path ise, script dizinine göre ayarla
    if not os.path.isabs(config_path):
        script_dir = Path(__file__).parent
        config_path = str(script_dir / config_path)
    
    if not os.path.exists(config_path):
        return {}
    
    with open(config_path, 'r', encoding='utf-8') as f:
        data = yaml.safe_load(f)
    
    return data.get('global_settings', {})


# ============================================================================
# İNSAN ALGILAMA (YOLOv8)
# ============================================================================

# Global YOLOv8 model (bir kez yüklenir)
_yolo_model = None

def get_yolo_model():
    """YOLOv8 model'ini lazy load et"""
    global _yolo_model
    if _yolo_model is None:
        print("[YOLO] Model yükleniyor...")
        # YOLOv8s model (small versiyonu - daha hızlı)
        _yolo_model = YOLO('yolov8s.pt')
        print("[YOLO] Model yüklendi")
    return _yolo_model


def detect_humans_in_image(image_path: Path, min_coverage_ratio: float = 0.15) -> Tuple[bool, float, int]:
    """
    Görüntüde insan (tüm vücut) algıla - YOLOv8 kullanarak
    
    Args:
        image_path: Görüntü dosya yolu
        min_coverage_ratio: İnsanın görüntüyü kaplaması gereken minimum oran (varsayılan %15)
    
    Returns:
        (has_human, coverage_ratio, person_count): İnsan var mı, kaplama oranı, insan sayısı
    """
    try:
        # YOLOv8 model'ini al
        model = get_yolo_model()
        
        # Görüntüyü analiz et
        results = model(str(image_path))
        
        # Person class ID = 0 (COCO dataset'inde)
        person_class_id = 0
        
        # Görüntü boyutlarını al
        img = Image.open(image_path)
        img_width, img_height = img.size
        total_image_area = img_width * img_height
        
        # Person detection'ları bul
        person_detections = []
        total_person_area = 0
        
        for result in results:
            boxes = result.boxes
            for box in boxes:
                # Class ID kontrolü (0 = person)
                if int(box.cls) == person_class_id:
                    # Bounding box koordinatları [x1, y1, x2, y2]
                    x1, y1, x2, y2 = box.xyxy[0].cpu().numpy()
                    person_width = x2 - x1
                    person_height = y2 - y1
                    person_area = person_width * person_height
                    
                    person_detections.append({
                        'box': [x1, y1, x2, y2],
                        'confidence': float(box.conf),
                        'area': person_area
                    })
                    total_person_area += person_area
        
        if not person_detections:
            return False, 0.0, 0
        
        # Kaplama oranı
        coverage_ratio = total_person_area / total_image_area
        has_human = coverage_ratio >= min_coverage_ratio
        
        return has_human, coverage_ratio, len(person_detections)
        
    except Exception as e:
        print(f"[UYARI] İnsan algılama hatası: {e}")
        import traceback
        traceback.print_exc()
        # Hata durumunda güvenli tarafta kal (insan yok kabul et)
        return False, 0.0, 0


def capture_snapshot_with_retry(
    controller: CameraController,
    camera_config: CameraConfig,
    target_name: str,
    ptz_coords: Dict,
    save_dir: Path,
    snapshots_root: Optional[Path] = None,
    max_retries: int = 5,
    min_coverage_ratio: float = 0.15,
    retry_delay: float = 3.0
) -> Optional[Path]:
    """
    Snapshot al ve insan algılanırsa tekrar çek
    
    Args:
        controller: Kamera kontrolcüsü
        camera_config: Kamera konfigürasyonu
        target_name: Hedef adı
        ptz_coords: PTZ koordinatları (azimuth, elevation, zoom)
        save_dir: Kayıt dizini
        snapshots_root: Snapshots kök dizini (S3 key oluşturmak için, opsiyonel)
        max_retries: Maksimum tekrar deneme sayısı
        min_coverage_ratio: İnsanın görüntüyü kaplaması gereken minimum oran
        retry_delay: Tekrar deneme arası bekleme süresi (saniye)
    
    Returns:
        Snapshot dosya yolu veya None
    """
    az = ptz_coords['azimuth']
    el = ptz_coords['elevation']
    zz = ptz_coords['zoom']
    
    for attempt in range(max_retries):
        try:
            # PTZ'yi pozisyona götür (ilk denemede zaten götürülmüştü, ama tekrar denemelerde gerekli)
            if attempt > 0:
                print(f"[RETRY {attempt}] PTZ pozisyonuna gidiliyor...")
                controller.move_ptz(az, el, zz)
                time.sleep(camera_config.move_settle_seconds)
            
            # Snapshot al
            if attempt == 0:
                filename_prefix = target_name
            else:
                filename_prefix = f"{target_name}_retry{attempt+1}"
            
            snapshot_path = controller.take_snapshot(
                target_name=filename_prefix,
                save_dir=save_dir,
                snapshots_root=snapshots_root
            )
            
            if not snapshot_path:
                print(f"[UYARI] Snapshot alınamadı (deneme {attempt+1}/{max_retries})")
                if attempt < max_retries - 1:
                    time.sleep(retry_delay)
                    continue
                return None
            
            # İnsan algılama kontrolü
            has_human, coverage_ratio, person_count = detect_humans_in_image(
                snapshot_path, 
                min_coverage_ratio
            )
            
            if has_human:
                print(f"[İNSAN ALGILANDI] {target_name} - Kaplama: {coverage_ratio:.1%}, İnsan sayısı: {person_count}")
                
                # İnsan algılanan görüntüyü sil
                try:
                    snapshot_path.unlink()
                    print(f"[SİLİNDİ] İnsan algılanan görüntü silindi: {snapshot_path.name}")
                except Exception as e:
                    print(f"[UYARI] Görüntü silinemedi: {e}")
                
                if attempt < max_retries - 1:
                    print(f"[RETRY {attempt+1}/{max_retries}] İnsan algılandı, tekrar çekiliyor...")
                    time.sleep(retry_delay)
                    continue
                else:
                    # Maksimum deneme sayısına ulaşıldı ve hala insan var
                    print(f"[UYARI] Maksimum deneme sayısına ulaşıldı ({max_retries}) ve hala insan algılandı")
                    print(f"[ATLANDI] {target_name} - İnsan algılanan görüntü kaydedilmedi")
                    return None
            else:
                # İnsan yok, görüntü kabul edilebilir
                if person_count > 0:
                    print(f"[OK] {target_name} - İnsan var ama kaplama yeterli değil ({coverage_ratio:.1%} < {min_coverage_ratio:.1%})")
                
                # S3'e yükle (insan kontrolünden sonra)
                if snapshots_root is None:
                    # save_dir = snapshots_root / camera_id olduğu için parent'ı al
                    snapshots_root = save_dir.parent
                
                s3_key = _to_snapshot_s3_key(snapshot_path, snapshots_root)
                s3_result = _upload_file_to_s3(snapshot_path, s3_key, content_type="image/jpeg")
                
                if s3_result:
                    print(f"[✓] {camera_config.camera_id} - S3'e yüklendi: {s3_key}")
                    # S3'e başarıyla yüklendikten sonra lokal dosyayı sil
                    try:
                        snapshot_path.unlink()
                        print(f"[✓] {camera_config.camera_id} - Lokal dosya silindi: {snapshot_path.name}")
                    except Exception as e:
                        print(f"[UYARI] Lokal dosya silinemedi: {e}")
                else:
                    print(f"[UYARI] {camera_config.camera_id} - S3'e yüklenemedi, lokal dosya korunuyor: {snapshot_path.name}")
                
                return snapshot_path
                
        except Exception as e:
            print(f"[HATA] Snapshot alma hatası (deneme {attempt+1}/{max_retries}): {e}")
            if attempt < max_retries - 1:
                time.sleep(retry_delay)
                continue
            return None
    
    return None


# ============================================================================
# SNAPSHOT ALMA FONKSİYONLARI
# ============================================================================

def capture_camera_snapshots(camera_id: str, config_path: str = 'cameras.yaml') -> Dict:
    """
    Tek bir kameradan tüm PTZ hedeflerini yakala
    """
    try:
        # Konfigürasyonu yükle
        camera_configs = load_camera_configs(config_path)
        global_settings = get_global_settings(config_path)
        
        if camera_id not in camera_configs:
            raise ValueError(f"Kamera bulunamadı: {camera_id}")
        
        camera_config = camera_configs[camera_id]
        controller = CameraController(camera_config)
        
        # Snapshot klasörü
        snapshots_root = Path(global_settings.get('snapshots_root', 'snapshots'))
        if not snapshots_root.is_absolute():
            script_dir = Path(__file__).parent
            snapshots_root = script_dir / snapshots_root
        
        # Tüm hedefleri yakala
        results = []
        total_targets = len(camera_config.ptz_targets)
        
        print(f"\n[{camera_id}] {camera_config.name}")
        print(f"[{camera_id}] {total_targets} hedef işlenecek...")
        
        for i, (target_name, coords) in enumerate(camera_config.ptz_targets.items()):
            try:
                az = coords["azimuth"]
                el = coords["elevation"]
                zz = coords["zoom"]

                # PTZ hareket
                print(f"[{camera_id}] {target_name} → PTZ hareket: az={az}, el={el}, zoom={zz} ({i+1}/{total_targets})")
                controller.move_ptz(az, el, zz)
                
                # Bekleme süresi
                time.sleep(camera_config.move_settle_seconds)
                
                # Snapshot al (insan algılama ile tekrar çekme özelliği ile)
                ptz_coords = {'azimuth': az, 'elevation': el, 'zoom': zz}
                snapshot_path = capture_snapshot_with_retry(
                    controller=controller,
                    camera_config=camera_config,
                    target_name=target_name,
                    ptz_coords=ptz_coords,
                    save_dir=snapshots_root / camera_id,
                    snapshots_root=snapshots_root,
                    max_retries=5,  # Maksimum 5 deneme
                    min_coverage_ratio=0.15,  # %15 kaplama oranı
                    retry_delay=3.0  # 3 saniye bekleme
                )
                
                if snapshot_path:
                    results.append({
                        'target_name': target_name,
                        'snapshot_path': str(snapshot_path),
                        'ptz_coords': {'azimuth': az, 'elevation': el, 'zoom': zz},
                        'timestamp': get_turkey_time().isoformat()
                    })
                else:
                    print(f"[UYARI] {camera_id} - {target_name} snapshot alınamadı")
                
            except Exception as e:
                print(f"[HATA] {camera_id} - {target_name} yakalanırken hata: {e}")
                continue
        
        print(f"[✓] {camera_id} - Tamamlandı: {len(results)}/{total_targets} snapshot alındı")
        
        return {
            'camera_id': camera_id,
            'total_snapshots': len(results),
            'snapshots': results,
            'timestamp': get_turkey_time().isoformat()
        }
        
    except Exception as e:
        print(f"[HATA] {camera_id} - Snapshot yakalama başarısız: {e}")
        raise


def process_single_configuration(config_path: str) -> Dict:
    """Tek bir konfigürasyon dosyasındaki tüm kameraları işle"""
    camera_configs = load_camera_configs(config_path)
    camera_ids = list(camera_configs.keys())

    print(f"\n{'='*60}")
    print(f"[SİSTEM] Konfigürasyon: {config_path}")
    print(f"[SİSTEM] {len(camera_ids)} kameradan snapshot alınıyor...")
    print(f"{'='*60}")

    if not camera_ids:
        print(f"[SİSTEM] {config_path} dosyasında kamera tanımı bulunamadı, atlanıyor.")
        return {
            'config_path': config_path,
            'total_cameras': 0,
            'camera_ids': [],
            'total_snapshots': 0,
            'snapshot_results': [],
            'status': 'no_cameras',
            'timestamp': get_turkey_time().isoformat(),
        }

    # Tüm kameraları sırayla işle
    snapshot_results = []
    for idx, camera_id in enumerate(camera_ids, 1):
        try:
            print(f"\n[{idx}/{len(camera_ids)}] Kamera işleniyor: {camera_id}")
            result = capture_camera_snapshots(camera_id, config_path)
            snapshot_results.append(result)
        except Exception as e:
            print(f"[HATA] {camera_id} işlenirken hata: {e}")
            continue

    total_snapshots = sum(r['total_snapshots'] for r in snapshot_results if r)

    summary = {
        'config_path': config_path,
        'total_cameras': len(camera_ids),
        'camera_ids': camera_ids,
        'total_snapshots': total_snapshots,
        'snapshot_results': snapshot_results,
        'timestamp': get_turkey_time().isoformat(),
        'status': 'success'
    }

    print(f"\n[SİSTEM] Tamamlandı - {config_path}: {len(camera_ids)} kamera, {total_snapshots} snapshot")
    return summary


def process_all_cameras(config_path: str = 'cameras.yaml', additional_configs: List[str] = None) -> Dict:
    """
    Tüm kameralardan snapshot al
    Varsayılan olarak cameras.yaml ve cameras_reyon_genel.yaml birlikte işlenir
    """
    DEFAULT_ADDITIONAL_CONFIGS = ['cameras_reyon_genel.yaml']
    
    try:
        config_paths: List[str] = [config_path]

        if additional_configs:
            config_paths.extend(additional_configs)
        elif config_path == 'cameras.yaml':
            script_dir = Path(__file__).parent
            for extra_path in DEFAULT_ADDITIONAL_CONFIGS:
                extra_file = script_dir / extra_path
                if extra_file.exists():
                    config_paths.append(extra_path)
                    print(f"[SİSTEM] Ek konfigürasyon bulundu: {extra_path}")

        combined_snapshot_results: List[Dict] = []
        config_runs: List[Dict] = []

        for cfg in config_paths:
            summary = process_single_configuration(cfg)
            config_runs.append(summary)
            combined_snapshot_results.extend(summary.get('snapshot_results', []))

        total_cameras = sum(run.get('total_cameras', 0) for run in config_runs)
        total_snapshots = sum(run.get('total_snapshots', 0) for run in config_runs)

        overall_summary = {
            'total_cameras': total_cameras,
            'total_snapshots': total_snapshots,
            'snapshot_results': combined_snapshot_results,
            'config_runs': config_runs,
            'timestamp': get_turkey_time().isoformat(),
            'status': 'success'
        }

        return overall_summary

    except Exception as e:
        print(f"[HATA] Sistem çalıştırma başarısız: {e}")
        raise


# ============================================================================
# ANA PROGRAM
# ============================================================================

def main():
    """Ana program"""
    print("=" * 60)
    print("MULTI-CAMERA SNAPSHOT SYSTEM")
    print("=" * 60)
    print()
    print("Tüm kameralardan snapshot alınıyor...")
    print("Bu işlem birkaç dakika sürebilir (kamera sayısına göre)")
    print()
    
    start_time = get_turkey_time()
    
    try:
        # Tüm kameraları işle
        result = process_all_cameras()
        
        end_time = get_turkey_time()
        duration = (end_time - start_time).total_seconds()
        
        print()
        print("=" * 60)
        print("TAMAMLANDI!")
        print("=" * 60)
        print()
        print(f"Toplam Kamera: {result.get('total_cameras', 0)}")
        print(f"Toplam Snapshot: {result.get('total_snapshots', 0)}")
        print(f"Süre: {duration:.1f} saniye")
        print()
        
        # Detaylı rapor
        for run in result.get('config_runs', []):
            print(f"Konfigürasyon: {run.get('config_path')}")
            print(f"  Kamera sayısı: {run.get('total_cameras', 0)}")
            print(f"  Snapshot sayısı: {run.get('total_snapshots', 0)}")
            for cam_result in run.get('snapshot_results', []):
                cam_id = cam_result.get('camera_id')
                count = cam_result.get('total_snapshots', 0)
                print(f"    - {cam_id}: {count} snapshot")
            print()
        
        # Snapshot klasörü bilgisi
        script_dir = Path(__file__).parent
        snapshots_dir = script_dir / 'snapshots'
        print(f"Snapshot'lar şu klasörde: {snapshots_dir}")
        print()
        
    except KeyboardInterrupt:
        print("\n\n[İPTAL] Kullanıcı tarafından durduruldu")
    except Exception as e:
        print(f"\n\n[HATA] Sistem hatası: {e}")
        import traceback
        traceback.print_exc()


if __name__ == '__main__':
    main()

