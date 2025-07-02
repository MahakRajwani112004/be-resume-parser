from fastapi import APIRouter
from app.services.resume_parser import build_resume_database_async

router = APIRouter()

@router.get("/status")
async def status():
    db = await build_resume_database_async(load_from_cache=True)
    return {"chunks": len(db)}