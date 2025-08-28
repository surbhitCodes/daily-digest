import aiohttp
import os
import base64
import smtplib
from datetime import datetime
from summarizer import format_slack_digest
from email.message import EmailMessage
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow

SCOPES = ['https://mail.google.com/']

async def send_to_slack(summary_text: str, raw_articles: list = None):
    webhook_url = os.getenv("SLACK_WEBHOOK_URL")
    if not webhook_url:
        return
    if raw_articles:
        formatted = format_slack_digest(raw_articles)
    else:
        formatted = summary_text
    async with aiohttp.ClientSession() as session:
        await session.post(webhook_url, json={"text": formatted})

def get_gmail_oauth2_creds():
    if os.path.exists("token.json"):
        creds = Credentials.from_authorized_user_file("token.json", SCOPES)
    else:
        flow = InstalledAppFlow.from_client_secrets_file("connect_mail.json", SCOPES)
        creds = flow.run_local_server(port=0)
        with open("token.json", "w") as token:
            token.write(creds.to_json())
    if creds and creds.expired and creds.refresh_token:
        creds.refresh(Request())
    return creds

async def send_email(summary: str):
    creds = get_gmail_oauth2_creds()
    access_token = creds.token

    email_from = os.getenv("EMAIL_FROM")
    email_to = os.getenv("EMAIL_TO")
    date = datetime.now().strftime("%Y-%m-%d")
    msg = EmailMessage()
    msg["From"] = email_from
    msg["To"] = email_to
    msg["Subject"] = f"**Daily News Digest -- {date}**"
    msg.set_content(summary)

    auth_string = f"user={email_from}\1auth=Bearer {access_token}\1\1"
    auth_bytes = base64.b64encode(auth_string.encode("utf-8")).decode("utf-8")

    with smtplib.SMTP("smtp.gmail.com", 587) as smtp:
        smtp.ehlo()
        smtp.starttls()
        smtp.ehlo()
        smtp.docmd("AUTH", "XOAUTH2 " + auth_bytes)
        smtp.send_message(msg)

async def notify(summary: str):
    await send_to_slack(summary)
    # await send_email(summary)
