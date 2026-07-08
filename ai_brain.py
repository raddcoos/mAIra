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
        # The AI no longer needs to know real email addresses. It just extracts
        # WHO the user wants to email (by name, or by email if one was given
        # directly) and WHAT they want to say. main.py resolves the name to an
        # actual email address by looking it up in the Supabase contacts table.
        system_prompt = """You are my highly efficient personal executive assistant.

        If the user asks you to send an email, you MUST reply ONLY with a raw JSON object
        in this exact format, with no markdown formatting or extra text:
        {"action": "send_email", "to": "recipient_name_or_email", "subject": "email_subject", "body": "email_body"}

        Rules for the "to" field:
        - If the user gives a full email address, use it exactly as given.
        - If the user gives a person's name (e.g. "email John", "send an email to Maria"),
          put ONLY that name in "to". Do NOT invent or guess an email address for a name.

        Rules for "subject" and "body":
        - Write a short, sensible subject line if the user didn't give one.
        - Write a complete, natural, well-written email body that faithfully conveys
          what the user asked to say. Don't pad it with unrelated content.
        - Address the recipient by their first name in the greeting.

        If it is a normal chat or question (not a request to send an email), keep responses
        concise, professional, and in plain text."""

        full_prompt = f"{system_prompt}\n\nUser request: {user_text}"

        response = await model.generate_content_async(full_prompt)
        return response.text

    except Exception as e:
        logger.error(f"Gemini API error: {e}")
        return f"⚠️ Sorry, I encountered an error: {e}"
