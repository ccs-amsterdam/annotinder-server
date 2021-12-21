"""
Backend for CCS Annotator
"""

import argparse, re
import json
import logging

from amcat4annotator import auth
from amcat4annotator.db import User


def get_token(args):
    u = User.get_or_none(User.email == args.user)
    if not u:
        logging.error(f"User {args.user} does not exist!")
        return
    print(auth.get_token(u))


def add_user(args):
    u = User.get_or_none(User.email == args.user)
    if u:
        logging.error(f"User {args.user} already exists!")
        return
    u = User.create(email=args.user, is_admin=args.admin)
    print(auth.get_token(u))


def list_users(args):
    for u in User.select().execute():
        print(json.dumps(dict(id=u.id, email=u.email, is_admin=u.is_admin)))


def check_token(args):
    u = auth.verify_token(args.token)
    print(json.dumps(dict(id=u.id, email=u.email, is_admin=u.is_admin)))


def email(s):
    if not re.match(r".*@.*\.\w+", s):
        raise ValueError(f"Cannot parse email {s}")
    return s

parser = argparse.ArgumentParser(description=__doc__)
subparsers = parser.add_subparsers(dest="action", title="action", help='Action to perform:', required=True)
p = subparsers.add_parser('get_token', help='Get token for a user')
p.add_argument("user", type=email, help="Email address of the user")
p.set_defaults(func=get_token)

p = subparsers.add_parser('add_user', help='Create a new user')
p.add_argument("user", type=email, help="Email address of the new user")
p.add_argument("--admin", action="store_true", help="Set user to admin (root / superuser)")
p.set_defaults(func=add_user)

p = subparsers.add_parser('list_users', help='List all userse')
p.set_defaults(func=list_users)

p = subparsers.add_parser('check_token', help='List all userse')
p.add_argument("token", help="Token to verify")
p.set_defaults(func=check_token)

args = parser.parse_args()

args.func(args)