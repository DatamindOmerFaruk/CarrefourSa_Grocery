import boto3
import os

# S3 Ayarları (environment variables'dan alınır)
S3_ENDPOINT_URL = os.getenv("S3_ENDPOINT_URL", "https://161cohesity.carrefoursa.com:3000")
S3_ACCESS_KEY_ID = os.getenv("S3_ACCESS_KEY_ID", "")
S3_SECRET_ACCESS_KEY = os.getenv("S3_SECRET_ACCESS_KEY", "")
S3_BUCKET_NAME = os.getenv("S3_BUCKET_NAME", "Grocery")

def upload_image(local_image_path, object_name):
    s3 = boto3.client(
        "s3",
        endpoint_url=S3_ENDPOINT_URL,
        aws_access_key_id=S3_ACCESS_KEY_ID,
        aws_secret_access_key=S3_SECRET_ACCESS_KEY,
        verify=False  # Gerekirse SSL hatalarında kapatılabilir

    )

    s3.upload_file(local_image_path, S3_BUCKET_NAME, object_name)

    print(f"{local_image_path} → s3://{S3_BUCKET_NAME}/{object_name} yüklendi.")

if __name__ == "__main__":

    # Örnek kullanım

    upload_image("resim.jpg", "images/resim.jpg")
 