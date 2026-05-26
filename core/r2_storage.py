import os
import boto3
from botocore.exceptions import ClientError
from botocore.config import Config
from boto3.s3.transfer import TransferConfig
from dotenv import load_dotenv
import time

load_dotenv()

R2_BUCKET = "canaldark"
R2_ACCOUNT_ID = os.getenv("R2_ACCOUNT_ID", "e9468fd5f172fa2f2a9485f6159d2a0c")

def get_r2_client():
    access_key = os.getenv("R2_ACCESS_KEY_ID")
    secret_key = os.getenv("R2_SECRET_ACCESS_KEY")
    
    if not access_key or not secret_key:
        return None
    
    boto_config = Config(
        retries={'max_attempts': 5, 'mode': 'standard'},
        connect_timeout=60,
        read_timeout=120,
        max_pool_connections=50
    )
    
    return boto3.client(
        's3',
        endpoint_url=f"https://{R2_ACCOUNT_ID}.r2.cloudflarestorage.com",
        aws_access_key_id=access_key,
        aws_secret_access_key=secret_key,
        region_name='auto',
        config=boto_config
    )

def list_all_objects():
    client = get_r2_client()
    if not client: return {}
    
    objects = {}
    try:
        paginator = client.get_paginator('list_objects_v2')
        pages = paginator.paginate(Bucket=R2_BUCKET)
        for page in pages:
            for obj in page.get('Contents', []):
                objects[obj['Key']] = obj['Size']
    except Exception as e:
        print(f"Erro ao listar objetos do R2: {e}")
        
    return objects

def upload_file(local_path, s3_key, max_retries=3):
    client = get_r2_client()
    if not client: return False
    
    transfer_config = TransferConfig(
        multipart_threshold=1024 * 25,     # 25MB
        max_concurrency=10,
        multipart_chunksize=1024 * 25,     # 25MB
        use_threads=True
    )

    for attempt in range(max_retries):
        try:
            client.upload_file(local_path, R2_BUCKET, s3_key, Config=transfer_config)
            return True
        except Exception as e:
            print(f"Erro ao fazer upload para R2 ({s3_key}) - tentativa {attempt + 1}/{max_retries}: {e}")
            if attempt < max_retries - 1:
                time.sleep(5)
            else:
                return False

def download_file(s3_key, local_path):
    client = get_r2_client()
    if not client: return False
    try:
        os.makedirs(os.path.dirname(local_path), exist_ok=True)
        client.download_file(R2_BUCKET, s3_key, local_path)
        return True
    except Exception as e:
        print(f"Erro ao baixar do R2 ({s3_key}): {e}")
        return False

def generate_presigned_url(s3_key, expiration=3600):
    client = get_r2_client()
    if not client: return None
    try:
        url = client.generate_presigned_url(
            'get_object',
            Params={'Bucket': R2_BUCKET, 'Key': s3_key},
            ExpiresIn=expiration
        )
        return url
    except Exception as e:
        print(f"Erro ao gerar URL presignada ({s3_key}): {e}")
        return None
