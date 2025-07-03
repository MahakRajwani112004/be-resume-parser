# app/services/query_router.py

import logging
from app.config.config import settings

# --- IMPORTANT ---
# Import the shared ASYNC client, not a new synchronous one.
# Let's assume it's defined in resume_parser.py as our central point.
from app.services.resume_parser import openai_client 

# Define the prompts here so they can be imported by the search service
AGENT_SYSTEM_PROMPTS = {
    "skill_matcher": "You are an AI assistant specializing in matching technical skills...",
    "experience_analyzer": "You are an AI assistant specializing in analyzing work experience...",
    "relevancy_scorer": "You are an AI assistant that scores and ranks candidates...",
    "seniority_detector": "You are an AI assistant that detects job seniority...",
    "general_analyzer": "You are a world-class HR AI Assistant..."
}

# --- RENAMED and made ASYNC ---
async def route_query_async(query: str) -> str:
    """
    Asynchronously classifies the user's query to select an agent role.
    """
    system_prompt = "Classify the HR query into one of: skill_matcher, experience_analyzer, relevancy_scorer, seniority_detector, general_analyzer. Return ONLY the label."
    try:
        # Use the shared ASYNC client and the `await` keyword
        response = await openai_client.chat.completions.create(
            model=settings.OPENAI_MODEL,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": query}
            ],
            max_tokens=20, # Increased slightly for safety
        )
        agent_name = response.choices[0].message.content.strip().lower().replace("'", "").replace('"', "")
        
        # Validate the response against our known agents
        if agent_name in AGENT_SYSTEM_PROMPTS:
            return agent_name
        else:
            logging.warning(f"Router returned unknown agent '{agent_name}'. Defaulting to general_analyzer.")
            return "general_analyzer"

    except Exception as e:
        logging.error(f"Query routing failed: {e}. Defaulting to general_analyzer.")
        return "general_analyzer"