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

NO_PLACEHOLDER_RULES = """
- NEVER use placeholder brackets or fill-in-the-blank text of any kind
  (e.g. "[Your Name]", "[Date]", "[Venue]", "___"). If a detail wasn't given to you
  and isn't essential, simply leave it out of the email rather than marking it as missing.
- Write the body as finished, ready-to-send text — not a template.
"""


def _sender_sign_off_rule(sender_name: str = None) -> str:
    if sender_name:
        # Verbatim instruction: the model must not shorten, abbreviate, or
        # otherwise "improve" this string — copy it exactly as given.
        return (
            f'If a sign-off is appropriate, sign off using EXACTLY this text, unchanged, '
            f'character for character: "{sender_name}". Do not shorten it, do not use only '
            f'part of it (e.g. only a first name), do not change its capitalization.'
        )
    return "You don't know the sender's name — sign off without a name (e.g. just \"Best regards,\")."


async def get_ai_response(user_text: str, sender_name: str = None) -> str:
    if not model:
        return "AI is currently offline. Missing API Key."

    try:
        system_prompt = f"""You are my highly efficient personal executive assistant.

        If the user asks you to send an email, you MUST reply ONLY with a raw JSON object
        in this exact format, with no markdown formatting or extra text:
        {{"action": "send_email", "to": "recipient_name_or_email", "subject": "email_subject", "body": "email_body"}}

        Rules for the "to" field:
        - If the user gives a full email address, use it exactly as given.
        - If the user gives a person's name (e.g. "email John", "send an email to Maria"),
          put ONLY that name in "to". Do NOT invent or guess an email address for a name.

        Rules for "subject" and "body":
        - Write a short, sensible subject line if the user didn't give one.
        - Write a complete, natural, human-sounding email body that faithfully conveys
          what the user asked to say, using any specific details they gave (dates, places, etc.).
        - {_sender_sign_off_rule(sender_name)}
        {NO_PLACEHOLDER_RULES}

        If it is a normal chat or question (not a request to send an email), keep responses
        concise, professional, and in plain text."""

        full_prompt = f"{system_prompt}\n\nUser request: {user_text}"

        response = await model.generate_content_async(full_prompt)
        return response.text

    except Exception as e:
        logger.error(f"Gemini API error: {e}")
        return f"⚠️ Sorry, I encountered an error: {e}"


async def rewrite_email(original_request: str, previous_subject: str, previous_body: str, sender_name: str = None) -> str:
    """
    Produces a fresh subject/body for the same email request, worded differently
    from the previous draft. Returns raw model text (expected to be JSON with
    "subject" and "body" keys) — caller is responsible for parsing/validating it.
    """
    if not model:
        return None

    try:
        system_prompt = f"""You are my highly efficient personal executive assistant.

        The user already asked you to draft an email, and you wrote a first draft. They want
        a REWRITE — a noticeably different version in wording and structure, while keeping the
        same intent and any specific details (dates, places, names) from their original request.

        Reply ONLY with a raw JSON object in this exact format, with no markdown formatting or
        extra text:
        {{"subject": "email_subject", "body": "email_body"}}

        Rules:
        - {_sender_sign_off_rule(sender_name)}
        {NO_PLACEHOLDER_RULES}
        - Do not simply reword a sentence or two — write a genuinely fresh draft."""

        full_prompt = (
            f"{system_prompt}\n\n"
            f"Original user request: {original_request}\n\n"
            f"Previous subject: {previous_subject}\n"
            f"Previous body:\n{previous_body}\n\n"
            f"Write a new version now."
        )

        response = await model.generate_content_async(full_prompt)
        return response.text

    except Exception as e:
        logger.error(f"Gemini API error during rewrite: {e}")
        return None
