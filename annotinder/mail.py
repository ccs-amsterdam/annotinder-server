import os
import smtplib
import ssl
from datetime import datetime
from dotenv import load_dotenv
from email.mime.text import MIMEText

load_dotenv()

CTX = ssl.create_default_context()
PASSWORD = os.getenv('EMAIL_PASSWORD')    # Your app password goes here
SENDER = os.getenv('EMAIL_ADDRESS')    # Your e-mail address
PORT = os.getenv('EMAIL_PORT', '')
if PORT == '': PORT = 465

def send_email(to: str, subject: str, body: str) -> None:
    msg = MIMEText(body, 'html')
    msg['Subject'] = subject
    msg['From'] = 'AnnoTinder <{email}>'.format(email=SENDER)
    msg['To'] = to
    print(msg)
   
    with smtplib.SMTP_SSL(os.getenv('EMAIL_SMTP'), port=PORT, context=CTX) as server:
        #server.set_debuglevel(1)
        server.login(SENDER, PASSWORD)
        server.sendmail(SENDER, to, msg.as_string())

magic_link_template = """\
<div style="display: flex; flex-direction: column;">
    <div style="margin: auto; font-size: 20px; text-align: center;">
        <h2 style="color: #2185d0;">Sign in to AnnoTinder</h2>
        <br/>
        <div style="background: #eee; padding: 10px; border-radius: 10px;">
            <p>
                Click on
                <br/>
                <a href="www.google.com">THIS LINK</a>
            </p>
            <h3 style="border-bottom: 1px solid black; line-height: 0.1em; margin: 30px 0 30px">
                <span style="background: #eee; color: #777777;": padding: 0 20px;>OR</span>
            </h3>
            <p>
                Use this code
                <br/>
                <b style="color: #2185d0;">{secret}</b>
            </p>
        <div>
    </div>
</div>
"""

def send_magic_link(name: str, email:str, secret: str):
    time = datetime.utcnow().strftime('%H:%M:%S')
    subject = "Login link for {name} ({time})".format(name=name, time=time)
    body = magic_link_template.format(name=name,secret=secret)
    send_email(email, subject, body)

if __name__ == '__main__':
    #send_email('kasperwelbers@gmail.com', 'test', 'Dit. En dit heeft ook <a href="www.google.com">een link naar Google</a>')
    send_magic_link('Kasper','kasperwelbers@gmail.com', 'super secret')
