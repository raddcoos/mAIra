import os
import base64
from email.message import EmailMessage
from googleapiclient.discovery import build
from google.oauth2.credentials import Credentials

def send_gmail(to_email, subject, body):
    # This assumes you have a token.json in your directory
    creds = Credentials.from_authorized_user_file('token.json', ['https://www.googleapis.com/auth/gmail.send'])
    service = build('gmail', 'v1', credentials=creds)
    
    message = EmailMessage()
    message.set_content(body)
    message['To'] = to_email
    message['Subject'] = subject
    
    raw_message = base64.urlsafe_b64encode(message.as_bytes()).decode()
    service.users().messages().send(userId="me", body={'raw': raw_message}).execute()
