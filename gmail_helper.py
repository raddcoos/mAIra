import os
import logging
import requests

logger = logging.getLogger(__name__)

# Why this file changed:
# Railway's Hobby/Free plans block outbound SMTP traffic (ports 25, 465, 587)
# to prevent spam abuse. That's what was causing:
#   [Errno 101] Network is unreachable
# Brevo's API sends email over plain HTTPS instead of SMTP, so it works fine
# on Railway's Hobby plan without any port restrictions.

BREVO_API_KEY = os.getenv("BREVO_API_KEY")
BREVO_SENDER_EMAIL = os.getenv("BREVO_SENDER_EMAIL")  # the address you verify in Brevo
BREVO_SENDER_NAME = os.getenv("BREVO_SENDER_NAME", "AI Assistant")

BREVO_API_URL = "https://api.brevo.com/v3/smtp/email"


def send_gmail(to_email: str, subject: str, body: str):
    """
    Sends an email via the Brevo HTTPS API.
    Keeps the same name/signature as before so main.py doesn't need changes.
    """
    if not BREVO_API_KEY:
        raise RuntimeError("Missing BREVO_API_KEY environment variable.")
    if not BREVO_SENDER_EMAIL:
        raise RuntimeError("Missing BREVO_SENDER_EMAIL environment variable.")

    payload = {
        "sender": {"name": BREVO_SENDER_NAME, "email": BREVO_SENDER_EMAIL},
        "to": [{"email": to_email}],
        "subject": subject,
        "htmlContent": f"<p>{body}</p>",
    }
    headers = {
        "accept": "application/json",
        "api-key": BREVO_API_KEY,
        "content-type": "application/json",
    }

    response = requests.post(BREVO_API_URL, json=payload, headers=headers, timeout=15)

    if response.status_code >= 400:
        logger.error(f"Brevo API error {response.status_code}: {response.text}")
        raise RuntimeError(f"Brevo API error {response.status_code}: {response.text}")

    logger.info(f"Email sent to {to_email} via Brevo. Message ID: {response.json().get('messageId')}")
    return response.json()
