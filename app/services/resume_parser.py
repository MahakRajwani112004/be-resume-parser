# app/services/resume_parser.py

import os
import json
import re
import logging
import numpy as np
import asyncio
from app.config.config import settings
from sentence_transformers import SentenceTransformer
import openai

# --- Models can stay here as the central point of truth ---
embedding_model = SentenceTransformer("all-MiniLM-L6-v2")
openai_client = openai.AsyncOpenAI(api_key=settings.OPENAI_API_KEY)

# --- NEW: Define the intelligent prompt ---
INTELLIGENT_PARSER_PROMPT = """
You are an expert resume parser and data analyst. Your task is to convert the provided resume text into a single, valid JSON object following the enhanced schema below.

**Enhanced JSON Schema:**
{
  "name": "string",
  "contact": {"email": "string", "phone": "string", "linkedin": "string"},
  "summary": "string",
  "total_experience_years": "float | null",
  "skills": ["string"],
  "projects": [{{"name": "string", "description": "string", "technologies": ["string"]}}],
  "work_experience": [{
    "job_title": "string",
    "company": "string",
    "duration": "string",
    "experience_type": "string",
    "calculated_duration_years": "float | null",
    "responsibilities": ["string"],
    
  }],
  "education": [{"degree": "string", "institution": "string", "year": "string"}]
}

**CRITICAL INSTRUCTIONS:**
1.  For `work_experience`: Analyze each role for its `experience_type` (must be one of: "full-time", "part-time", "internship", "freelance", "contract"). For `calculated_duration_years`, calculate the duration from the dates as a number (e.g., 2.5). Use `null` if unclear.
2.  For `total_experience_years`: Sum the `calculated_duration_years` for ONLY "full-time" and "contract" roles.

Your entire response MUST be only the valid JSON object.
"""

# --- MODIFIED: This function now uses the intelligent prompt and adds logging ---
async def parse_resume_from_text(raw_text: str):
    """
    Takes raw text and returns a richly structured JSON from the AI.
    """
    try:
        response = await openai_client.chat.completions.create(
            model=settings.OPENAI_MODEL,
            messages=[
                # Use the new, more powerful prompt
                {"role": "system", "content": INTELLIGENT_PARSER_PROMPT}, 
                {"role": "user", "content": f"Resume Text:\n{raw_text}"},
            ],
            response_format={"type": "json_object"}
        )
        
        parsed_json = json.loads(response.choices[0].message.content)
        
        # --- NEW: Log the parsed data so you can see it! ---
        # We use json.dumps with an indent to "pretty-print" the JSON in your terminal.
        candidate_name = parsed_json.get("name", "Unknown Candidate")
        logging.info(f"--- Parsed Data for: {candidate_name} ---\n{json.dumps(parsed_json, indent=2)}\n-----------------------------------")
        
        return parsed_json
        
    except Exception as e:
        logging.error(f"AI parsing failed with intelligent prompt: {e}", exc_info=True)
        return None

# --- MODIFIED: Update this function to use the new rich data ---
def create_text_chunks(parsed_json, resume_filename):
    """
    Creates text chunks for embedding, now including the new experience details.
    """
    chunks = []
    name = parsed_json.get("name", "N/A")
    summary = parsed_json.get("summary", "")
    skills = ", ".join(parsed_json.get("skills", []))
    
    # Use the new, more accurately calculated total experience
    total_exp = parsed_json.get("total_experience_years", "N/A")
    
    chunks.append({
        "resume_filename": resume_filename,
        "chunk_type": "profile",
        "text": f"Candidate Name: {name}. Summary: {summary}. Skills: {skills}. Calculated Relevant Experience: {total_exp} years.",
        "candidate_name": name
    })
    
    for i, exp in enumerate(parsed_json.get("work_experience", [])):
        # Add the new fields to the chunk text to make them searchable!
        exp_type = exp.get("experience_type", "N/A")
        calc_dur = exp.get("calculated_duration_years", "N/A")
        
        text = (f"Work Experience: {exp.get('job_title')} at {exp.get('company')}. "
                f"Type: {exp_type}. Duration: {calc_dur} years. "
                f"Responsibilities: {' '.join(exp.get('responsibilities', []))}")
                
        chunks.append({
            "resume_filename": resume_filename, 
            "chunk_type": f"exp_{i}", 
            "text": text, 
            "candidate_name": name
        })
        
    for i, proj in enumerate(parsed_json.get("projects", [])):
        text = f"Project: {proj.get('name')}. Description: {proj.get('description')}. Tech: {', '.join(proj.get('technologies', []))}"
        chunks.append({"resume_filename": resume_filename, "chunk_type": f"proj_{i}", "text": text, "candidate_name": name})
        
    return chunks