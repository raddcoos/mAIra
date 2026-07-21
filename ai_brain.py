# ai_brain.py
import os
import json
import logging
import httpx
import google.generativeai as genai

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

# Which engine to try first: "ollama" or "gemini".
# Set PRIMARY_AI=gemini on Railway any time you want to bypass Ollama entirely
# (e.g. your PC/tunnel is off for a while) without touching code.
PRIMARY_AI = os.getenv("PRIMARY_AI", "ollama").lower()

# Base URL of your Cloudflare Tunnel pointing at your PC's Ollama server,
# e.g. "https://your-tunnel-name.trycloudflare.com" (no trailing slash).
OLLAMA_URL = os.getenv("OLLAMA_URL", "").rstrip("/")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "qwen3.5:9b")
OLLAMA_TIMEOUT = float(os.getenv("OLLAMA_TIMEOUT_SECONDS", "20"))

# Base URL of the tunnel pointing at your PC's local Whisper server
# (whisper_server.py), e.g. "https://your-whisper-tunnel.trycloudflare.com".
WHISPER_URL = os.getenv("WHISPER_URL", "").rstrip("/")
WHISPER_TIMEOUT = float(os.getenv("WHISPER_TIMEOUT_SECONDS", "30"))

# When true, appends a small "(via ollama)" / "(via gemini)" tag to plain chat
# replies (never to the send_email JSON) so you can visually confirm which
# engine answered, without having to check Railway logs.
DEBUG_AI_SOURCE = os.getenv("DEBUG_AI_SOURCE", "false").lower() == "true"

if GEMINI_API_KEY:
    genai.configure(api_key=GEMINI_API_KEY)
    gemini_model = genai.GenerativeModel('gemini-2.5-flash')
else:
    logger.warning("Gemini API key missing! Gemini fallback will not work.")
    gemini_model = None

NO_PLACEHOLDER_RULES = """
- NEVER use placeholder brackets or fill-in-the-blank text of any kind
  (e.g. "[Your Name]", "[Date]", "[Venue]", "___"). If a detail wasn't given to you
  and isn't essential, simply leave it out of the email rather than marking it as missing.
- Write the body as finished, ready-to-send text — not a template.
"""


def _sender_sign_off_rule(sender_name: str = None) -> str:
    if sender_name:
        return (
            f'If a sign-off is appropriate, sign off using EXACTLY this text, unchanged, '
            f'character for character: "{sender_name}". Do not shorten it, do not use only '
            f'part of it (e.g. only a first name), do not change its capitalization.'
        )
    return "You don't know the sender's name — sign off without a name (e.g. just \"Best regards,\")."


# ---------------------------------------------------------------------------
# Low-level engine callers
# ---------------------------------------------------------------------------

async def _call_ollama(system_prompt: str, user_text: str) -> str:
    """Calls your Ollama server (local or via tunnel) using its native /api/chat
    endpoint. Raises on any failure (timeout, connection error, bad response) so
    the caller can fall back to Gemini."""
    if not OLLAMA_URL:
        raise RuntimeError("OLLAMA_URL is not set")

    payload = {
        "model": OLLAMA_MODEL,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_text},
        ],
        "stream": False,
    }

    async with httpx.AsyncClient(timeout=OLLAMA_TIMEOUT) as client:
        resp = await client.post(f"{OLLAMA_URL}/api/chat", json=payload)
        resp.raise_for_status()
        data = resp.json()

    content = data.get("message", {}).get("content", "")
    if not content:
        raise RuntimeError(f"Ollama returned an empty response: {data}")
    return content.strip()


async def _call_gemini(system_prompt: str, user_text: str) -> str:
    if not gemini_model:
        raise RuntimeError("Gemini model is not configured (missing API key)")

    full_prompt = f"{system_prompt}\n\nUser request: {user_text}"
    response = await gemini_model.generate_content_async(full_prompt)
    return response.text


async def _run_with_fallback(system_prompt: str, user_text: str) -> tuple[str, str]:
    """Tries the primary engine, automatically falls back to the other one on
    failure. Returns (text, engine_used). engine_used is "error" if both fail."""
    engines = ["ollama", "gemini"] if PRIMARY_AI == "ollama" else ["gemini", "ollama"]

    last_error = None
    for engine in engines:
        try:
            if engine == "ollama":
                text = await _call_ollama(system_prompt, user_text)
            else:
                text = await _call_gemini(system_prompt, user_text)
            logger.info(f"AI response served by: {engine}")
            return text, engine
        except Exception as e:
            logger.warning(f"{engine} failed: {e}")
            last_error = e
            continue

    logger.error(f"All AI engines failed. Last error: {last_error}")
    return f"⚠️ Sorry, I encountered an error: {last_error}", "error"


def _maybe_tag_source(text: str, engine: str) -> str:
    """Appends a debug tag like '(via ollama)' to plain-text replies when
    DEBUG_AI_SOURCE is enabled. Never tags JSON (send_email actions), since
    that would break the caller's parsing."""
    if not DEBUG_AI_SOURCE or engine == "error":
        return text
    stripped = text.strip()
    if stripped.startswith("{") and stripped.endswith("}"):
        try:
            json.loads(stripped)
            return text  # it's valid JSON (a send_email action) — don't touch it
        except (json.JSONDecodeError, ValueError):
            pass
    return f"{text}\n\n_(via {engine})_"


# ---------------------------------------------------------------------------
# Public functions (same signatures/behavior as before)
# ---------------------------------------------------------------------------

async def get_ai_response(user_text: str, sender_name: str = None) -> str:
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

    text, engine = await _run_with_fallback(system_prompt, user_text)
    return _maybe_tag_source(text, engine)


async def rewrite_email(original_request: str, previous_subject: str, previous_body: str, sender_name: str = None) -> str:
    """
    Produces a fresh subject/body for the same email request, worded differently
    from the previous draft. Returns raw model text (expected to be JSON with
    "subject" and "body" keys) — caller is responsible for parsing/validating it.
    """
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

    user_text = (
        f"Original user request: {original_request}\n\n"
        f"Previous subject: {previous_subject}\n"
        f"Previous body:\n{previous_body}\n\n"
        f"Write a new version now."
    )

    try:
        text, engine = await _run_with_fallback(system_prompt, user_text)
        if engine == "error":
            return None
        return _maybe_tag_source(text, engine)
    except Exception as e:
        logger.error(f"rewrite_email error: {e}")
        return None


async def _call_local_whisper(audio_bytes: bytes, mime_type: str) -> str:
    """Calls your local whisper_server.py (via tunnel). Raises on any failure
    so the caller can fall back to Gemini."""
    if not WHISPER_URL:
        raise RuntimeError("WHISPER_URL is not set")

    ext = mime_type.split("/")[-1] if "/" in mime_type else "ogg"
    files = {"file": (f"audio.{ext}", audio_bytes, mime_type)}

    async with httpx.AsyncClient(timeout=WHISPER_TIMEOUT) as client:
        resp = await client.post(f"{WHISPER_URL}/transcribe", files=files)
        resp.raise_for_status()
        data = resp.json()

    if "error" in data:
        raise RuntimeError(f"Whisper server error: {data['error']}")

    text = data.get("text", "")
    if not text:
        raise RuntimeError(f"Whisper server returned an empty transcript: {data}")
    return text.strip()


async def _call_gemini_transcription(audio_bytes: bytes, mime_type: str) -> str:
    if not gemini_model:
        raise RuntimeError("Gemini model is not configured (missing API key)")

    response = await gemini_model.generate_content_async([
        {"mime_type": mime_type, "data": bytes(audio_bytes)},
        "Transcribe this audio to plain text, in the language it was spoken in. "
        "Output ONLY the transcription itself — no quotation marks, no commentary, "
        "no labels like 'Transcript:'.",
    ])
    return response.text.strip()


async def transcribe_audio(audio_bytes: bytes, mime_type: str = "audio/ogg") -> str:
    """
    Transcribes a voice note to plain text. Tries your local Whisper server first
    (free, via tunnel), and automatically falls back to Gemini's native audio
    understanding if Whisper is unreachable. Returns the transcript, or None if
    both fail.
    """
    engines = ["whisper", "gemini"] if PRIMARY_AI == "ollama" else ["gemini", "whisper"]

    last_error = None
    for engine in engines:
        try:
            if engine == "whisper":
                text = await _call_local_whisper(audio_bytes, mime_type)
            else:
                text = await _call_gemini_transcription(audio_bytes, mime_type)
            logger.info(f"Transcription served by: {engine}")
            return text
        except Exception as e:
            logger.warning(f"{engine} transcription failed: {e}")
            last_error = e
            continue

    logger.error(f"All transcription engines failed. Last error: {last_error}")
    return None
