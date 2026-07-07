# ai_brain.py
import os
import logging
import google.generativeai as genai

logger = logging.getLogger(__name__)

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

model = genai.GenerativeModel('gemini-2.5-flash', generation_config={"response_mime_type": "application/json"})

if GEMINI_API_KEY:
    genai.configure(api_key=GEMINI_API_KEY)
    model = genai.GenerativeModel('gemini-1.5-flash')
else:
    logger.warning("Gemini API key missing! AI responses will fail.")
    model = None

# Add 'async' to the function definition
async def get_ai_response(user_text: str) -> str:
    if not model:
        return "AI is currently offline. Missing API Key."
    
    try:
        system_prompt = "You are my highly efficient personal executive assistant. Keep responses concise, professional, and helpful."
        full_prompt = f"{system_prompt}\n\nUser request: {user_text}"
        
        # Use the async version of generate_content and add 'await'
        response = await model.generate_content_async(full_prompt)
        return response.text
        
    except Exception as e:
        logger.error(f"Gemini API error: {e}")
        return f"⚠️ Sorry, I encountered an error: {e}"
