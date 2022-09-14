"""
Backend for CCS Annotator
"""

import argparse, os, stat
import json
import logging
import hashlib


import uvicorn


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

def create_env(args):
    if os.path.exists('.env'):
        raise Exception('.env already exists')
    env = ENV_TEMPLATE.format(secret=hashlib.sha256().hexdigest())
    with open('.env', 'w') as f:
        f.write(env)
    os.chmod('.env', 0o600)
    print('Created .env')


def run(args):
    logging.info(f"Starting server at port {args.port}, reload={not args.noreload}")
    uvicorn.run("annotinder.api:app", host="0.0.0.0", port=args.port, reload=not args.noreload)
    
def _print_user(u: User):
    print(json.dumps(dict(id=u.id, name=u.name, is_admin=u.is_admin, password=bool(u.password))))


def get_token(args):
    u = User.get_or_none(User.name == args.user)
    if not u:
        logging.error(f"User {args.user} does not exist!")
        return
    print(get_token(u))


def add_user(args):
    db = SessionLocal()
    u = crud_user.create_user(db, args.user, args.password, args.admin)
    if u:
        _print_user(u)


def list_users(args):
    for u in User.select().execute():
        _print_user(u)


def check_token(args):
    u = verify_token(args.token)
    _print_user(u)


def password(args):    
    db = SessionLocal()
    u = db.query(User).filter(User.name == args.user).first()
    if args.setpassword:
        logging.info(f"Setting password for {args.user}")
        u.password = hash_password(args.password)
        db.flush()
        db.commit()
        _print_user(u)
    else:
        ok = verify_password(args.password, u.password)
        print(f"Password {'matched' if ok else 'did not match'}")



parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--verbose", "-v", help="Verbose (debug) output", action="store_true", default=False)
subparsers = parser.add_subparsers(dest="action", title="action", help='Action to perform:', required=True)
p = subparsers.add_parser('run', help='Run the annotator in dev mode')
p.add_argument("-p", '--port', help='Port', default=5000)
p.add_argument("--no-reload", action='store_true', dest='noreload', help='Disable reload (when files change)')
p.set_defaults(func=run)

p = subparsers.add_parser('get_token', help='Get token for a user')
p.add_argument("user", help="username of the user")
p.set_defaults(func=get_token)

p = subparsers.add_parser('create_env', help='Create the .env file with a random secret key')
p.set_defaults(func=create_env)

p = subparsers.add_parser('get_token', help='Get token for a user')
p.add_argument("user", help="username of the user")
p.set_defaults(func=get_token)

p = subparsers.add_parser('add_user', help='Create a new user')
p.add_argument("user", help="username of the new user")
p.add_argument("--admin", action="store_true", help="Set user to admin (root / superuser)")
p.add_argument("--password", help="Add a password for this user")
p.set_defaults(func=add_user)

p = subparsers.add_parser('list_users', help='List all users')
p.set_defaults(func=list_users)

p = subparsers.add_parser('check_token', help='Check a token')
p.add_argument("token", help="Token to verify")
p.set_defaults(func=check_token)

p = subparsers.add_parser('password', help='Check or set a password')
p.add_argument("user", help="User to login as")
p.add_argument("password", help="Password")
p.add_argument("--set", dest="setpassword", action="store_true", help="Set password")
p.set_defaults(func=password)

args = parser.parse_args()

logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO,
                    format='[%(asctime)s %(name)-12s %(levelname)-5s] %(message)s')

args.func(args)
