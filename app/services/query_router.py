import openai
from app.config.config import settings

client = openai.OpenAI(api_key=settings.OPENAI_API_KEY)

def route_query(query: str) -> str:
    system_prompt = "Classify the HR query into one of: skill_matcher, experience_analyzer, relevancy_scorer, seniority_detector, general_analyzer. Return ONLY the label."
    try:
        response = client.chat.completions.create(
            model=settings.OPENAI_MODEL,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": query}
            ],
            max_tokens=10,
        )
        return response.choices[0].message.content.strip().lower()
    except Exception:
        return "general_analyzer"
