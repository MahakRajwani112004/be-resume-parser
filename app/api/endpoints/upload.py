from fastapi import APIRouter, UploadFile, File
from typing import List
from app.services import clounidary_utils

router = APIRouter()

@router.post("/upload")
async def upload(files: List[UploadFile] = File(...)):
    return await clounidary_utils.upload_files(files)