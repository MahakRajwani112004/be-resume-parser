from fastapi import APIRouter, HTTPException, Request
from app.services import search_service

router = APIRouter()

@router.post("/search")
async def search(payload: dict):
    query = payload.get("query")
    if not query:
        raise HTTPException(status_code=400, detail="Missing query")
    return await search_service.search_resumes(query)