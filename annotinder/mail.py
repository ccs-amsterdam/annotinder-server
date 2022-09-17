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

# MESSAGE_TEMPLATE = """\
# From: "AnnoTinder"
# Subject: {subject}

# {body}
# """

def send_email(to: str, subject: str, body: str) -> None:
    msg = smtplib.MIMEText(body, 'html')
    msg['Subject'] = subject
    msg['From'] = 'AnnoTinder'
    msg['To'] = to
    
    with smtplib.SMTP_SSL(os.getenv('EMAIL_SMTP'), port=PORT, context=CTX) as server:
        server.login(SENDER, PASSWORD)
        server.sendmail(SENDER, to, msg)

def send_magic_link(name: str, email:str, secret: str):
    subject = "AnnoTinder Login link for {name}".format(name=name)
    body = "Hi {name}!\n\n".format(name=name) +
           "Please use the following link to login to AnnoTinder:\n\n"
    send_email(email, subject, body)

if __name__ == '__main__':
    send_email('kasperwelbers@gmail.com', 'test', 'Dit. En dit heeft ook <a href="www.google.com">een link naar Google</a>')

