import boto3

ACCESS_KEY = "sWxdTl3ERx7myBE1qpW06_haVvuhATcdsmBbqaWkXYU"
SECRET_KEY = "Ti9Fonk3wYyG5PMx5LaGUmlcVyCuqsE5BLVV5vv8PU0"
ENDPOINT_URL = "https://361cohesity.carrefoursa.com:3000"
BUCKET_NAME = "Grocery"

def upload_image(local_image_path, object_name):
    s3 = boto3.client(
        "s3",
        endpoint_url=ENDPOINT_URL,

        aws_access_key_id=ACCESS_KEY,

        aws_secret_access_key=SECRET_KEY,

        verify=False  # Gerekirse SSL hatalarında kapatılabilir

    )

    s3.upload_file(local_image_path, BUCKET_NAME, object_name)

    print(f"{local_image_path} → s3://{BUCKET_NAME}/{object_name} yüklendi.")

if __name__ == "__main__":

    # Örnek kullanım

    upload_image("resim.jpg", "images/resim.jpg")
 