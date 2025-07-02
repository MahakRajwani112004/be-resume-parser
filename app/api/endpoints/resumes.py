from fastapi import APIRouter, HTTPException
import json
import logging

router = APIRouter()

@router.get("/resumes")
async def list_resumes():
    try:
        with open("resume_url_map.json", "r") as f:
            resume_map = json.load(f)
        return {
            "resumes": [{"filename": filename, "url": url} for filename, url in resume_map.items()]
        }
    except FileNotFoundError:
        return {"resumes": []}
    except Exception as e:
        logging.error(f"Failed to load resume list: {e}")
        raise HTTPException(status_code=500, detail="Failed to load resume list")