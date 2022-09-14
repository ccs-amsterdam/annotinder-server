import os
import smtplib
import ssl
from dotenv import load_dotenv

load_dotenv()

CTX = ssl.create_default_context()
PASSWORD = os.getenv('EMAIL_PASSWORD')    # Your app password goes here
SENDER = os.getenv('EMAIL_ADDRESS')    # Your e-mail address
PORT = os.getenv('EMAIL_PORT', '')
if PORT == '': PORT = 465

MESSAGE_TEMPLATE = """\
From: "AnnoTinder"
Subject: {subject}

{body}
"""

def send_email(to: str, subject: str, body: str) -> None:
    message = MESSAGE_TEMPLATE.format(subject=subject, body=body)
    
    with smtplib.SMTP_SSL(os.getenv('EMAIL_SMTP'), port=PORT, context=CTX) as server:
        server.login(SENDER, PASSWORD)
        server.sendmail(SENDER, to, message)

if __name__ == '__main__':
    send_email('kasperwelbers@gmail.com', 'test', 'dit')

