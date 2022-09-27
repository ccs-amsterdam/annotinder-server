"""
Backend for CCS Annotator
"""

import argparse, os, stat
import json
import logging
import secrets
import uvicorn
from email_validator import validate_email

from annotinder.api import app

from annotinder.crud import crud_user
from annotinder.models import User
from annotinder.database import SessionLocal
from annotinder.auth import get_token, verify_token, hash_password, verify_password

ENV_TEMPLATE = """\
# Config for sending emails. e.g., using Gmail (see readme)
EMAIL_SMTP=smtp.gmail.com
EMAIL_ADDRESS=
EMAIL_PASSWORD=

# Config for setting up GITHUB oauth2 login (see readme)
GITHUB_CALLBACK_URL=https://annotinder.com
GITHUB_CLIENT_ID=
GITHUB_CLIENT_SECRET=

SECRET_KEY=${secret}
"""


def run(args):
    logging.info(f"Starting server at port {args.port}, reload={not args.noreload}")
    uvicorn.run("annotinder.api:app", host="0.0.0.0", port=args.port, reload=not args.noreload)


def create_env(args):
    if os.path.exists('.env'):
        raise Exception('.env already exists')
    env = ENV_TEMPLATE.format(secret=secrets.token_hex(nbytes=16))
    with open('.env', 'w') as f:
        f.write(env)
    os.chmod('.env', 0o600)
    print('Created .env')


def _print_user(u: User):
    print(json.dumps(dict(id=u.id, name=u.name, is_admin=u.is_admin, password=bool(u.password))))


def add_user(args):
    db = SessionLocal()
    email = validate_email(args.email).email
    u = crud_user.register_user(db, args.name, email, args.password, args.admin)
    if u:
        _print_user(u)


def password(args):    
    db = SessionLocal()
    u = db.query(User).filter(User.email == args.email).first()
    if args.setpassword:
        logging.info(f"Setting password for {args.email}")
        u.password = hash_password(args.password)
        db.flush()
        db.commit()
        _print_user(u)
    else:
        ok = verify_password(args.password, u.password)
        print(f"Password {'matched' if ok else 'did not match'}")

def create_admin(args):
    db = SessionLocal()
    u = db.query(User).filter(User.email == args.email).first()
    if not u:
        logging.warning(f"User {args.email} does not exist")
    u.is_admin = not args.disable
    db.flush()
    db.commit()
    _print_user(u)




parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--verbose", "-v", help="Verbose (debug) output", action="store_true", default=False)
subparsers = parser.add_subparsers(dest="action", title="action", help='Action to perform:', required=True)

p = subparsers.add_parser('run', help='Run the annotator in dev mode')
p.add_argument("-p", '--port', help='Port', default=5000)
p.add_argument("--no-reload", action='store_true', dest='noreload', help='Disable reload (when files change)')
p.set_defaults(func=run)

p = subparsers.add_parser('create_env', help='Create the .env file with a random secret key')
p.set_defaults(func=create_env)

p = subparsers.add_parser('add_user', help='Create a new user')
p.add_argument("name", help="username of the new user")
p.add_argument("email", help="email of the new user")
p.add_argument("--admin", action="store_true", help="Set user to admin (root / superuser)")
p.add_argument("--password", help="Add a password for this user")
p.set_defaults(func=add_user)

p = subparsers.add_parser('password', help='Check or set a password')
p.add_argument("email", help="email address of registered user")
p.add_argument("password", help="Password")
p.add_argument("--set", dest="setpassword", action="store_true", help="Set password")
p.set_defaults(func=password)

p = subparsers.add_parser('create_admin', help='Turn existing user into admin')
p.add_argument("email", help="email address of registered user")
p.add_argument("--disable", action='store_true', help="Disable this user as admin")
p.set_defaults(func=create_admin)

args = parser.parse_args()

logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO,
                    format='[%(asctime)s %(name)-12s %(levelname)-5s] %(message)s')

args.func(args)
