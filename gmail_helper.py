import os
import smtplib
from email.message import EmailMessage

def send_gmail(to_email, subject, body):
    email_user = os.getenv("EMAIL_USER")
    email_pass = os.getenv("EMAIL_PASS")

    msg = EmailMessage()
    msg.set_content(body)
    msg['Subject'] = subject
    msg['From'] = email_user
    msg['To'] = to_email

    # Connect to Google's SMTP server
    with smtplib.SMTP_SSL('smtp.gmail.com', 465) as smtp:
        smtp.login(email_user, email_pass)
        smtp.send_message(msg)
