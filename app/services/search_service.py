import json
import numpy as np
from fastapi import HTTPException
from sklearn.metrics.pairwise import cosine_similarity
from sentence_transformers import SentenceTransformer
from app.services.resume_parser import build_resume_database_async
from app.services.query_router import route_query

embedding_model = SentenceTransformer("all-MiniLM-L6-v2")
RETRIEVAL_TOP_K = 15

async def search_resumes(query: str):
    db = await build_resume_database_async(load_from_cache=True)
    if not db:
        raise HTTPException(status_code=500, detail="Resume database is empty")

    q_embed = embedding_model.encode([query])[0]
    similarities = cosine_similarity([q_embed], [np.array(d["embedding"]) for d in db])[0]
    top_k = np.argsort(similarities)[::-1][:RETRIEVAL_TOP_K]
    context = [db[i]["metadata"] for i in top_k]

    ctx_str = "\n\n".join([
        f"Candidate: {c.get('candidate_name')}\n{c['text']}"
        for c in context
    ])

    routed_agent = route_query(query)
    final_prompt = f"""
You are a hiring AI. Role: {routed_agent}.
Query: \"{query}\"
Context:
{ctx_str}
List only the best matches with 2-line explanation each.
"""

    from openai import OpenAI
    client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
    try:
        response = client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": "You are a recruitment AI assistant."},
                {"role": "user", "content": final_prompt}
            ]
        )
        answer_text = response.choices[0].message.content
    except Exception:
        raise HTTPException(status_code=500, detail="LLM inference failed")

    name_to_filename = {
        c.get("candidate_name"): c.get("resume_filename")
        for c in context
        if c.get("candidate_name") and c.get("resume_filename")
    }

    try:
        with open("resume_url_map.json", "r") as f:
            resume_url_map = json.load(f)
    except FileNotFoundError:
        resume_url_map = {}

    mentioned = [name for name in name_to_filename if name.lower() in answer_text.lower()]
    preview_urls = [
        {"name": name, "resume_url": resume_url_map.get(name_to_filename[name])}
        for name in mentioned if name_to_filename.get(name) in resume_url_map
    ]

    return {
        "agent_used": routed_agent,
        "answer": answer_text,
        "preview_urls": preview_urls
    }
