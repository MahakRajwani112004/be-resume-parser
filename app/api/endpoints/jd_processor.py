from fastapi import APIRouter, UploadFile, File, HTTPException, Form
from typing import Optional, Union
from app.services.jd_parser import process_jd_file, create_jd_search_query
from app.services.search_service import search_resumes
import logging

router = APIRouter()

@router.post("/upload-jd", tags=["Job Description Processing"])
async def upload_and_process_jd(
    file: Optional[UploadFile] = File(None),
    raw_text: Optional[str] = Form(None)
):
    try:
        if not file and not raw_text:
            raise HTTPException(
                status_code=400,
                detail="Either a file or raw_text must be provided"
            )
        
        parsed_jd = None
        
        if file:
            allowed_types = [
                "application/pdf",
                "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                "text/plain"
            ]
            
            if file.content_type not in allowed_types and not any(
                file.filename.lower().endswith(ext) for ext in ['.pdf', '.docx', '.txt']
            ):
                raise HTTPException(
                    status_code=400,
                    detail="Unsupported file type. Please upload PDF, DOCX, or TXT files."
                )
            
            file_content = await file.read()
            if not file_content:
                raise HTTPException(
                    status_code=400,
                    detail="Empty file provided"
                )
            
            parsed_jd = await process_jd_file(file_content, file.filename, file.content_type)
            
        elif raw_text:
            from app.services.jd_parser import parse_jd_from_text
            parsed_jd = await parse_jd_from_text(raw_text.strip())
            
            if parsed_jd:
                parsed_jd["raw_text"] = raw_text
                parsed_jd["filename"] = "raw_text_input"
                parsed_jd["file_type"] = "text/plain"
        
        if not parsed_jd:
            raise HTTPException(
                status_code=422,
                detail="Failed to parse job description. Please check the file format and content."
            )
        
        search_query = create_jd_search_query(parsed_jd)
        
        if not search_query:
            raise HTTPException(
                status_code=422,
                detail="Failed to create search query from job description"
            )
        
        try:
            search_results = await search_resumes(search_query)
        except Exception as e:
            logging.error(f"Resume search failed: {e}")
            search_results = {
                "agent_used": "general_analyzer",
                "answer": "Resume search temporarily unavailable. Please try again later.",
                "preview_urls": []
            }
        
        return {
            "success": True,
            "message": "Job description processed successfully",
            "parsed_jd": {
                "job_title": parsed_jd.get("job_title"),
                "company": parsed_jd.get("company"),
                "location": parsed_jd.get("location"),
                "employment_type": parsed_jd.get("employment_type"),
                "experience_level": parsed_jd.get("experience_level"),
                "required_skills": parsed_jd.get("required_skills", []),
                "preferred_skills": parsed_jd.get("preferred_skills", []),
                "required_experience_years": parsed_jd.get("required_experience_years"),
                "key_technologies": parsed_jd.get("key_technologies", []),
                "summary": parsed_jd.get("summary")
            },
            "search_query_generated": search_query,
            "matching_results": search_results,
            "metadata": {
                "filename": parsed_jd.get("filename"),
                "file_type": parsed_jd.get("file_type"),
                "processing_agent": search_results.get("agent_used", "general_analyzer")
            }
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logging.error(f"Unexpected error in JD processing: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Internal server error: {str(e)}"
        )

@router.post("/analyze-jd", tags=["Job Description Processing"])
async def analyze_jd_only(
    file: Optional[UploadFile] = File(None),
    raw_text: Optional[str] = Form(None)
):
    try:
        if not file and not raw_text:
            raise HTTPException(
                status_code=400,
                detail="Either a file or raw_text must be provided"
            )
        
        parsed_jd = None
        
        if file:
            allowed_types = [
                "application/pdf",
                "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                "text/plain"
            ]
            
            if file.content_type not in allowed_types and not any(
                file.filename.lower().endswith(ext) for ext in ['.pdf', '.docx', '.txt']
            ):
                raise HTTPException(
                    status_code=400,
                    detail="Unsupported file type. Please upload PDF, DOCX, or TXT files."
                )
            
            file_content = await file.read()
            if not file_content:
                raise HTTPException(
                    status_code=400,
                    detail="Empty file provided"
                )
            
            parsed_jd = await process_jd_file(file_content, file.filename, file.content_type)
            
        elif raw_text:
            from app.services.jd_parser import parse_jd_from_text
            parsed_jd = await parse_jd_from_text(raw_text.strip())
            
            if parsed_jd:
                parsed_jd["raw_text"] = raw_text
                parsed_jd["filename"] = "raw_text_input"
                parsed_jd["file_type"] = "text/plain"
        
        if not parsed_jd:
            raise HTTPException(
                status_code=422,
                detail="Failed to parse job description. Please check the file format and content."
            )
        
        return {
            "success": True,
            "message": "Job description analyzed successfully",
            "parsed_jd": parsed_jd,
            "suggested_search_query": create_jd_search_query(parsed_jd)
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logging.error(f"Unexpected error in JD analysis: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Internal server error: {str(e)}"
        )