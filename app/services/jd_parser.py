
import os
import json
import logging
import asyncio
from typing import Optional, Dict, Any
from app.config.config import settings
from app.services.resume_parser import openai_client
import pypdf

from docx import Document


JD_PARSER_PROMPT = """
You are an expert job description parser and analyzer. Your task is to convert the provided job description text into a structured JSON object that will be used for matching with candidate resumes.

**Required JSON Schema:**
{
  "job_title": "string",
  "company": "string",
  "location": "string",
  "employment_type": "string",
  "experience_level": "string",
  "required_skills": ["string"],
  "preferred_skills": ["string"],
  "required_experience_years": "number | null",
  "education_requirements": ["string"],
  "responsibilities": ["string"],
  "qualifications": ["string"],
  "benefits": ["string"],
  "salary_range": "string | null",
  "industry": "string",
  "department": "string",
  "key_technologies": ["string"],
  "soft_skills": ["string"],
  "certifications": ["string"],
  "summary": "string"
}

**CRITICAL INSTRUCTIONS:**
1. Extract all technical skills and separate them into required vs preferred
2. Identify the minimum years of experience required
3. List all responsibilities and qualifications clearly
4. Categorize skills into hard skills (technical) and soft skills
5. Extract any mentioned certifications or educational requirements
6. Provide a comprehensive summary of the role

Your entire response MUST be only the valid JSON object.
"""

async def extract_text_from_pdf(file_content: bytes) -> str:
    try:
        import tempfile
        with tempfile.NamedTemporaryFile(delete=False, suffix='.pdf') as tmp_file:
            tmp_file.write(file_content)
            tmp_file_path = tmp_file.name
        
        text = ""
        with open(tmp_file_path, 'rb') as file:
            pdf_reader = pypdf.PdfReader(file)
            for page in pdf_reader.pages:
                text += page.extract_text() + "\n"
        
        os.unlink(tmp_file_path)
        
        return text.strip()
    except Exception as e:
        logging.error(f"Error extracting text from PDF: {e}")
        return ""

async def extract_text_from_docx(file_content: bytes) -> str:
    try:
        import tempfile
        with tempfile.NamedTemporaryFile(delete=False, suffix='.docx') as tmp_file:
            tmp_file.write(file_content)
            tmp_file_path = tmp_file.name
        
        doc = Document(tmp_file_path)
        text = ""
        for paragraph in doc.paragraphs:
            text += paragraph.text + "\n"
        
        os.unlink(tmp_file_path)
        
        return text.strip()
    except Exception as e:
        logging.error(f"Error extracting text from DOCX: {e}")
        return ""

async def parse_jd_from_text(raw_text: str) -> Optional[Dict[str, Any]]:
    try:
        response = await openai_client.chat.completions.create(
            model=settings.OPENAI_MODEL,
            messages=[
                {"role": "system", "content": JD_PARSER_PROMPT},
                {"role": "user", "content": f"Job Description Text:\n{raw_text}"},
            ],
            response_format={"type": "json_object"}
        )
        
        parsed_json = json.loads(response.choices[0].message.content)
        
        job_title = parsed_json.get("job_title", "Unknown Position")
        logging.info(f"--- Parsed JD for: {job_title} ---\n{json.dumps(parsed_json, indent=2)}\n-----------------------------------")
        
        return parsed_json
        
    except Exception as e:
        logging.error(f"JD parsing failed: {e}", exc_info=True)
        return None

async def process_jd_file(file_content: bytes, filename: str, content_type: str) -> Optional[Dict[str, Any]]:
    try:
        raw_text = ""
        
        if content_type == "application/pdf" or filename.lower().endswith('.pdf'):
            raw_text = await extract_text_from_pdf(file_content)
        elif content_type == "application/vnd.openxmlformats-officedocument.wordprocessingml.document" or filename.lower().endswith('.docx'):
            raw_text = await extract_text_from_docx(file_content)
        elif content_type == "text/plain" or filename.lower().endswith('.txt'):
            raw_text = file_content.decode('utf-8')
        else:
            logging.error(f"Unsupported file type: {content_type}")
            return None
        
        if not raw_text.strip():
            logging.error("No text extracted from file")
            return None
        
        parsed_jd = await parse_jd_from_text(raw_text)
        
        if parsed_jd:
            parsed_jd["raw_text"] = raw_text
            parsed_jd["filename"] = filename
            parsed_jd["file_type"] = content_type
            
        return parsed_jd
        
    except Exception as e:
        logging.error(f"Error processing JD file {filename}: {e}", exc_info=True)
        return None

def create_jd_search_query(parsed_jd: Dict[str, Any]) -> str:
    try:
        job_title = parsed_jd.get("job_title", "")
        required_skills = ", ".join(parsed_jd.get("required_skills", []))
        preferred_skills = ", ".join(parsed_jd.get("preferred_skills", []))
        key_technologies = ", ".join(parsed_jd.get("key_technologies", []))
        experience_years = parsed_jd.get("required_experience_years", 0)
        
        query_parts = []
        
        if job_title:
            query_parts.append(f"Job Title: {job_title}")
        
        if required_skills:
            query_parts.append(f"Required Skills: {required_skills}")
        
        if key_technologies:
            query_parts.append(f"Technologies: {key_technologies}")
        
        if experience_years:
            query_parts.append(f"Experience: {experience_years}+ years")
        
        if preferred_skills:
            query_parts.append(f"Preferred Skills: {preferred_skills}")
        
        search_query = ". ".join(query_parts)
        
        return search_query
        
    except Exception as e:
        logging.error(f"Error creating search query: {e}")
        return ""