# ai_brain.py
import os
import logging
import google.generativeai as genai

logger = logging.getLogger(__name__)

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

if GEMINI_API_KEY:
    genai.configure(api_key=GEMINI_API_KEY)
    model = genai.GenerativeModel('gemini-2.5-flash')
else:
    logger.warning("Gemini API key missing! AI responses will fail.")
    model = None

async def get_ai_response(user_text: str) -> str:
    if not model:
        return "AI is currently offline. Missing API Key."
    
    try:
        # We update the prompt to instruct Gemini to output JSON for email actions
        system_prompt = """You are my highly efficient personal executive assistant. 
        If the user asks you to send an email, you MUST reply ONLY with a raw JSON object in this exact format, with no markdown formatting or extra text:
        {"action": "send_email", "to": "email_address", "subject": "email_subject", "body": "email_body"}
        
        If it is a normal chat or question, keep responses concise, professional, and in plain text."""
        
        full_prompt = f"{system_prompt}\n\nUser request: {user_text}"
        
        response = await model.generate_content_async(full_prompt)
        return response.text
        
    except Exception as e:
        logger.error(f"Gemini API error: {e}")
        return f"⚠️ Sorry, I encountered an error: {e}"
