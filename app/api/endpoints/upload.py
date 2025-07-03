# app/routers/upload.py

from fastapi import APIRouter, UploadFile, File, HTTPException
from typing import List
from app.services import clounidary_utils

router = APIRouter()

@router.post("/upload", tags=["Resume Processing"])
async def upload_and_process(files: List[UploadFile] = File(...)):
    """
    This single endpoint now handles file uploads, processing, and database updates.
    """
    result = await clounidary_utils.upload_and_process_concurrently(files)
    if result.get("error"):
        raise HTTPException(status_code=422, detail=result["error"])
    return result