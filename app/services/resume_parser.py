import os
import json
import re
import logging
import requests
import numpy as np
import asyncio
from dotenv import load_dotenv
from pypdf import PdfReader
from app.config.config import settings
from sentence_transformers import SentenceTransformer
import openai

load_dotenv()
embedding_model = SentenceTransformer("all-MiniLM-L6-v2")

openai_client = openai.AsyncOpenAI(api_key=settings.OPENAI_API_KEY)

def extract_text_from_pdf(pdf_path):
    try:
        reader = PdfReader(pdf_path)
        return "\n".join([page.extract_text() for page in reader.pages if page.extract_text()])
    except Exception as e:
        logging.error(f"Error reading PDF {pdf_path}: {e}")
        return ""

def extract_json_blob(text):
    match = re.search(r"\{.*\}", text, re.DOTALL)
    return match.group(0) if match else text

def create_text_chunks(parsed_json, resume_filename):
    chunks = []
    name = parsed_json.get("name", "N/A")
    summary = parsed_json.get("summary", "")
    skills = ", ".join(parsed_json.get("skills", []))
    exp_years = parsed_json.get("total_experience_years", "N/A")
    chunks.append({
        "resume_filename": resume_filename,
        "chunk_type": "profile",
        "text": f"Candidate Name: {name}. Summary: {summary}. Skills: {skills}. Experience: {exp_years} years.",
        "candidate_name": name
    })
    for i, exp in enumerate(parsed_json.get("work_experience", [])):
        text = f"Worked at {exp.get('company')} as {exp.get('job_title')}. {exp.get('duration')} - {' '.join(exp.get('responsibilities', []))}"
        chunks.append({"resume_filename": resume_filename, "chunk_type": f"exp_{i}", "text": text, "candidate_name": name})
    for i, proj in enumerate(parsed_json.get("projects", [])):
        text = f"Project: {proj.get('name')}. Description: {proj.get('description')}. Tech: {', '.join(proj.get('technologies', []))}"
        chunks.append({"resume_filename": resume_filename, "chunk_type": f"proj_{i}", "text": text, "candidate_name": name})
    return chunks

async def repair_json_with_gpt(bad_json_text):
    system_prompt = "The following is a broken JSON. Fix it and return only valid JSON. No markdown, no explanation."
    try:
        response = await openai_client.chat.completions.create(
            model=settings.OPENAI_MODEL,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": bad_json_text}
            ]
        )
        return json.loads(extract_json_blob(response.choices[0].message.content))
    except Exception as e:
        logging.error(f"Repair failed: {e}")
        return None

async def process_resume(pdf_path, semaphore):
    async with semaphore:
        filename = os.path.basename(pdf_path)
        raw_text = extract_text_from_pdf(pdf_path)
        if not raw_text.strip():
            return []
        
        system_prompt = """You are a resume parser. Convert the text into valid JSON following this schema: {\n"name": "string", "contact": {"email": "string", "phone": "string", "linkedin": "string"},\n"summary": "string", "total_experience_years": "int", "skills": ["string"],\n"work_experience": [{"job_title": "string", "company": "string", "duration": "string", "responsibilities": ["string"]}],\n"projects": [{"name": "string", "description": "string", "technologies": ["string"]}],\n"education": [{"degree": "string", "institution": "string", "year": "string"}]\n}"""

        try:
            response = await openai_client.chat.completions.create(
                model=settings.OPENAI_MODEL,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": f"Resume Text:\n{raw_text}"},
                ]
            )
            response_text = response.choices[0].message.content
            try:
                parsed = json.loads(extract_json_blob(response_text))
            except json.JSONDecodeError:
                parsed = await repair_json_with_gpt(response_text)
            if parsed:
                return create_text_chunks(parsed, filename)
        except Exception as e:
            logging.error(f"Error processing {filename}: {e}")
        return []

async def build_resume_database_async(load_from_cache=False):
    PROCESSED_DATA_FILE = "processed_resume_data.json"
    UPLOAD_URL_MAP_FILE = "resume_url_map.json"

    if load_from_cache and os.path.exists(PROCESSED_DATA_FILE):
        with open(PROCESSED_DATA_FILE, "r") as f:
            data = json.load(f)
        for item in data:
            item["embedding"] = np.array(item["embedding"])
        return data

    try:
        with open(UPLOAD_URL_MAP_FILE, "r") as f:
            url_map = json.load(f)
    except FileNotFoundError:
        logging.error("resume_url_map.json not found.")
        return []

    temp_dir = "/tmp/resumes"
    os.makedirs(temp_dir, exist_ok=True)

    pdf_paths = []
    for filename, url in url_map.items():
        temp_path = os.path.join(temp_dir, filename)
        try:
            response = requests.get(url)
            with open(temp_path, "wb") as f:
                f.write(response.content)
            pdf_paths.append(temp_path)
        except Exception as e:
            logging.warning(f"Failed to download {url}: {e}")

    if not pdf_paths:
        logging.error("No resumes downloaded.")
        return []

    semaphore = asyncio.Semaphore(10)
    tasks = [process_resume(pdf_path, semaphore) for pdf_path in pdf_paths]
    results = await asyncio.gather(*tasks)

    all_chunks = []
    for chunk_list in results:
        all_chunks.extend(chunk_list)

    if not all_chunks:
        logging.warning("No chunks extracted.")
        return []

    texts = [chunk["text"] for chunk in all_chunks]
    embeddings = embedding_model.encode(texts, show_progress_bar=False)
    db = [{"embedding": emb.tolist(), "metadata": chunk} for emb, chunk in zip(embeddings, all_chunks)]

    with open(PROCESSED_DATA_FILE, "w") as f:
        json.dump(db, f, indent=2)

    return db