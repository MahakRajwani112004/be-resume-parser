# app/services/search_service.py

import json
import numpy as np
import os
import logging
from fastapi import HTTPException
from sklearn.metrics.pairwise import cosine_similarity
import asyncio

# --- Import shared models and clients ---
# It's good practice to initialize these once and import them where needed.
# Let's assume they are in resume_parser.py for now.
from app.services.resume_parser import embedding_model, openai_client
from app.services.query_router import route_query_async # Let's make the router async too

# --- Define constants centrally ---
PROCESSED_DATA_FILE = "processed_resume_data.json"
UPLOAD_URL_MAP_FILE = "resume_url_map.json"
RETRIEVAL_TOP_K = 15

# --- New helper function to just load the DB ---
def _load_database_from_file():
    """
    Safely loads the processed vector database from the JSON file.
    This is a fast, synchronous I/O operation.
    """
    if not os.path.exists(PROCESSED_DATA_FILE):
        logging.error(f"{PROCESSED_DATA_FILE} not found. Database must be built first.")
        return None
    try:
        with open(PROCESSED_DATA_FILE, "r") as f:
            db = json.load(f)
        # Convert embeddings back to numpy arrays for calculation
        for item in db:
            item["embedding"] = np.array(item["embedding"])
        return db
    except (json.JSONDecodeError, IOError) as e:
        logging.error(f"Failed to load or parse {PROCESSED_DATA_FILE}: {e}")
        return None

# --- Main search function, now fully async and simplified ---
async def search_resumes(query: str):
    """
    Performs a single-agent RAG search on the pre-processed resume database.
    """
    # 1. Load the database directly. No need to "build" it.
    db = _load_database_from_file()
    if not db:
        raise HTTPException(
            status_code=503, # Service Unavailable
            detail="Resume database is not available. Please upload resumes first."
        )

    # 2. Embed the query and find similar chunks (Retrieval)
    # The encode step is CPU-bound, so run it in an executor to not block the event loop.
    loop = asyncio.get_event_loop()
    q_embed = await loop.run_in_executor(None, embedding_model.encode, [query])
    q_embed = q_embed[0]

    db_embeddings = [d["embedding"] for d in db]
    similarities = cosine_similarity([q_embed], db_embeddings)[0]
    top_k_indices = np.argsort(similarities)[::-1][:RETRIEVAL_TOP_K]
    context_chunks = [db[i]["metadata"] for i in top_k_indices]

    context_str = "\n\n".join(
        [f"Candidate: {c.get('candidate_name', 'N/A')}\n{c['text']}" for c in context_chunks]
    )

    # 3. Route to an agent and call the LLM (Augmentation & Generation)
    # We use the shared async client.
    routed_agent_name = await route_query_async(query) # Assuming you make router async
    
    # Assuming AGENT_SYSTEM_PROMPTS is defined in query_router.py or a config file
    from app.services.query_router import AGENT_SYSTEM_PROMPTS 
    agent_specific_prompt = AGENT_SYSTEM_PROMPTS.get(routed_agent_name, AGENT_SYSTEM_PROMPTS["general_analyzer"])

    final_prompt = f"""
Your Role: {agent_specific_prompt}

User Query: "{query}"

Based on the context below, provide a direct answer. 
IMPORTANT: You MUST mention the full name for every candidate discussed (e.g., "Candidate Name: John Doe").

--- Resume Context ---
{context_str}
"""
    try:
        response = await openai_client.chat.completions.create(
            model="gpt-4o", # Or from settings
            messages=[
                {"role": "system", "content": "You are a helpful recruitment AI assistant."},
                {"role": "user", "content": final_prompt}
            ]
        )
        answer_text = response.choices[0].message.content
    except Exception as e:
        logging.error(f"LLM inference failed: {e}")
        raise HTTPException(status_code=500, detail="LLM inference failed")

    # 4. Extract preview URLs from the result
    name_to_filename = {
        c.get("candidate_name"): c.get("resume_filename")
        for c in context_chunks
        if c.get("candidate_name") and c.get("resume_filename")
    }

    try:
        with open(UPLOAD_URL_MAP_FILE, "r") as f:
            resume_url_map = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        resume_url_map = {}

    mentioned_names = [name for name in name_to_filename if name and name.lower() in answer_text.lower()]
    preview_urls = []
    for name in set(mentioned_names): # Use set to avoid duplicates
        filename = name_to_filename.get(name)
        if filename and filename in resume_url_map:
            preview_urls.append({
                "name": name, 
                "resume_url": resume_url_map[filename]
            })

    return {
        "agent_used": routed_agent_name,
        "answer": answer_text,
        "preview_urls": preview_urls
    }