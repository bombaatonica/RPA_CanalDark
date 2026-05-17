import os
import boto3
from botocore.exceptions import ClientError
from dotenv import load_dotenv

load_dotenv()

R2_BUCKET = "canaldark"
R2_ACCOUNT_ID = os.getenv("R2_ACCOUNT_ID", "e9468fd5f172fa2f2a9485f6159d2a0c")

def get_r2_client():
    access_key = os.getenv("R2_ACCESS_KEY_ID")
    secret_key = os.getenv("R2_SECRET_ACCESS_KEY")
    
    if not access_key or not secret_key:
        return None
        
    return boto3.client(
        's3',
        endpoint_url=f"https://{R2_ACCOUNT_ID}.r2.cloudflarestorage.com",
        aws_access_key_id=access_key,
        aws_secret_access_key=secret_key,
        region_name='auto'
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

def upload_file(local_path, s3_key):
    client = get_r2_client()
    if not client: return False
    try:
        client.upload_file(local_path, R2_BUCKET, s3_key)
        return True
    except Exception as e:
        print(f"Erro ao fazer upload para R2 ({s3_key}): {e}")
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
