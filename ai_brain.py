# ai_brain.py
import os
import logging
import google.generativeai as genai

logger = logging.getLogger(__name__)

# Initialize Gemini API
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

if GEMINI_API_KEY:
    genai.configure(api_key=GEMINI_API_KEY)
    # Using the fast and cost-effective flash model
    model = genai.GenerativeModel('gemini-1.5-flash')
else:
    logger.warning("Gemini API key missing! AI responses will fail.")
    model = None

def get_ai_response(user_text: str) -> str:
    """Processes the user text through Gemini and returns the response as a string."""
    if not model:
        return "AI is currently offline. Missing API Key."
    
    try:
        # Give Gemini a persona so it knows its job
        system_prompt = "You are my highly efficient personal executive assistant. Keep responses concise, professional, and helpful."
        full_prompt = f"{system_prompt}\n\nUser request: {user_text}"
        
        response = model.generate_content(full_prompt)
        return response.text
        
    except Exception as e:
        logger.error(f"Gemini API error: {e}")
        return "⚠️ Sorry, I encountered an error while processing that."
