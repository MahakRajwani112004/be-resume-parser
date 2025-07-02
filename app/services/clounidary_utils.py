import cloudinary
import cloudinary.uploader
import os
import json
from fastapi import UploadFile
from typing import List
from app.config.config  import settings

cloudinary.config(
    cloud_name=settings.CLOUDINARY_CLOUD_NAME,
    api_key=settings.CLOUDINARY_API_KEY,
    api_secret=settings.CLOUDINARY_API_SECRET
)

UPLOAD_URL_MAP_FILE = "resume_url_map.json"

async def upload_files(files: List[UploadFile]):
    uploaded_urls = []
    cloudinary_map = {}

    for file in files:
        result = cloudinary.uploader.upload(file.file, resource_type="image", folder="resumes")
        cloudinary_map[file.filename] = result["secure_url"]
        uploaded_urls.append({
            "filename": file.filename,
            "url": result["secure_url"]
        })

    if os.path.exists(UPLOAD_URL_MAP_FILE):
        with open(UPLOAD_URL_MAP_FILE, "r") as f:
            old_map = json.load(f)
    else:
        old_map = {}
    old_map.update(cloudinary_map)
    with open(UPLOAD_URL_MAP_FILE, "w") as f:
        json.dump(old_map, f, indent=2)

    return {"uploaded": uploaded_urls}
