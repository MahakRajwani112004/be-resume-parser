# app/services/clounidary_utils.py

import cloudinary
import cloudinary.uploader
import os
import json
import logging
import asyncio
from fastapi import UploadFile
from typing import List
from pypdf import PdfReader

# --- These services now need to know about each other ---
from app.config.config import settings
from app.services.resume_parser import (
    create_text_chunks, 
    parse_resume_from_text, # We will create this new helper
    embedding_model # Import the model to use it here
)

cloudinary.config(
    cloud_name=settings.CLOUDINARY_CLOUD_NAME,
    api_key=settings.CLOUDINARY_API_KEY,
    api_secret=settings.CLOUDINARY_API_SECRET
)

PROCESSED_DATA_FILE = "processed_resume_data.json"
UPLOAD_URL_MAP_FILE = "resume_url_map.json"

# --- New helper to read PDF from an in-memory stream ---
def _extract_text_from_stream(file_stream):
    try:
        reader = PdfReader(file_stream)
        return "\n".join([page.extract_text() for page in reader.pages if page.extract_text()])
    except Exception as e:
        logging.error(f"Error reading PDF stream: {e}")
        return ""

# --- New "Worker" Function: The core of our new logic ---
async def _process_single_file_end_to_end(file: UploadFile, semaphore: asyncio.Semaphore):
    """
    This is the concurrent worker. It handles the entire pipeline for ONE resume.
    """
    async with semaphore:
        filename = file.filename
        logging.info(f"[{filename}] Starting end-to-end processing.")
        try:
            # 1. Upload to Cloudinary
            logging.info(f"[{filename}] Uploading to Cloudinary...")
            upload_result = cloudinary.uploader.upload(
                file.file, resource_type="image", folder="resumes"
            )
            cloudinary_url = upload_result["secure_url"]
            logging.info(f"[{filename}] Upload successful. URL: {cloudinary_url}")
            
            # 2. Parse content
            await file.seek(0)
            raw_text = _extract_text_from_stream(file.file)
            if not raw_text.strip(): 
                logging.warning(f"[{filename}] No text extracted, skipping AI processing.")
                return None

            logging.info(f"[{filename}] Extracted {len(raw_text)} characters. Sending to AI for parsing.")
            parsed_json = await parse_resume_from_text(raw_text)
            if not parsed_json: 
                logging.error(f"[{filename}] AI parsing returned no data.")
                return None
            logging.info(f"[{filename}] AI parsing successful.")

            # 3. Create chunks
            logging.info(f"[{filename}] Creating text chunks from parsed JSON.")
            chunks = create_text_chunks(parsed_json, filename)
            logging.info(f"[{filename}] Created {len(chunks)} text chunks.")
            
            # 4. Create embeddings
            chunk_texts = [chunk['text'] for chunk in chunks]
            logging.info(f"[{filename}] Starting embedding for {len(chunk_texts)} chunks.")
            
            loop = asyncio.get_running_loop()
            embeddings = await loop.run_in_executor(None, embedding_model.encode, chunk_texts)
            logging.info(f"[{filename}] Embedding complete.")
            
            processed_chunks = [{"embedding": emb.tolist(), "metadata": chunk} for emb, chunk in zip(embeddings, chunks)]
            
            return {
                "filename": filename,
                "cloudinary_url": cloudinary_url,
                "processed_chunks": processed_chunks
            }
        except Exception as e:
            logging.error(f"[{filename}] An error occurred during end-to-end processing: {e}", exc_info=True)
            return None
# app/services/clounidary_utils.py

# ... (other code in the file is fine) ...

async def upload_and_process_concurrently(files: List[UploadFile]):
    """
    Manages the concurrent processing of all uploaded files.
    """
    CONCURRENT_REQUESTS = 10
    semaphore = asyncio.Semaphore(CONCURRENT_REQUESTS)
    
    tasks = [_process_single_file_end_to_end(file, semaphore) for file in files]
    results = await asyncio.gather(*tasks)
    
    successful_results = [res for res in results if res]
    if not successful_results:
        return {"error": "Failed to process any files."}
        
    # --- Update Master Files ---
    logging.info("Updating master database files with correct flat-list structure...")
    
    # 1. Load existing databases
    try:
        with open(PROCESSED_DATA_FILE, "r") as f:
            vector_db = json.load(f)
        # Ensure it's a list, otherwise start fresh
        if not isinstance(vector_db, list):
            logging.warning("Existing vector DB is not a list. Starting a new one.")
            vector_db = []
    except (FileNotFoundError, json.JSONDecodeError):
        vector_db = []
        
    try:
        with open(UPLOAD_URL_MAP_FILE, "r") as f:
            url_map = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        url_map = {}

    # 2. Add new data from successful workers
    newly_processed_files = []
    for result in successful_results:
        # --- THIS IS THE CRITICAL FIX ---
        # Use .extend() to add all chunk items from the result to the master list.
        # This creates the flat list structure.
        if "processed_chunks" in result and isinstance(result["processed_chunks"], list):
            vector_db.extend(result["processed_chunks"])
        
        # Add to URL map (this part was likely correct)
        url_map[result["filename"]] = result["cloudinary_url"]
        newly_processed_files.append(result["filename"])

    # 3. Save the updated databases back to disk
    with open(PROCESSED_DATA_FILE, "w") as f:
        json.dump(vector_db, f, indent=2)
        
    with open(UPLOAD_URL_MAP_FILE, "w") as f:
        json.dump(url_map, f, indent=2)
        
    logging.info(f"Database update complete. Total chunks in DB: {len(vector_db)}")
        
    return {
        "message": "Files uploaded and processed successfully.",
        "processed_files": newly_processed_files
    }