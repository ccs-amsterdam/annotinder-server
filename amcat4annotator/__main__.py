"""
Backend for CCS Annotator
"""

import argparse, re
import json
import logging

from amcat4annotator import auth
from amcat4annotator.db import User


def _print_user(u: User):
    print(json.dumps(dict(id=u.id, email=u.email, is_admin=u.is_admin, password=bool(u.password))))


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
    password = auth.hash_password(args.password) if args.password else None
    u = User.create(email=args.user, is_admin=args.admin, password=password)
    _print_user(u)


def list_users(args):
    for u in User.select().execute():
        _print_user(u)


def check_token(args):
    u = auth.verify_token(args.token)
    _print_user(u)


def password(args):
    u = User.get(User.email==args.user)
    if args.setpassword:
        logging.info(f"Setting password for {args.user}")
        u.password = auth.hash_password(args.password)
        u.save()
        _print_user(u)
    else:
        ok = auth.verify_password(args.password, u.password)
        print(f"Password {'matched' if ok else 'did not match'}")


def email(s):
    if not re.match(r".*@.*\.\w+", s):
        raise ValueError(f"Cannot parse email {s}")
    return s


parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--verbose", "-v", help="Verbose (debug) output", action="store_true", default=False)
subparsers = parser.add_subparsers(dest="action", title="action", help='Action to perform:', required=True)
p = subparsers.add_parser('get_token', help='Get token for a user')
p.add_argument("user", type=email, help="Email address of the user")
p.set_defaults(func=get_token)

p = subparsers.add_parser('add_user', help='Create a new user')
p.add_argument("user", type=email, help="Email address of the new user")
p.add_argument("--admin", action="store_true", help="Set user to admin (root / superuser)")
p.add_argument("--password", help="Add a password for this user")
p.set_defaults(func=add_user)

p = subparsers.add_parser('list_users', help='List all users')
p.set_defaults(func=list_users)

p = subparsers.add_parser('check_token', help='Check a token')
p.add_argument("token", help="Token to verify")
p.set_defaults(func=check_token)

p = subparsers.add_parser('password', help='Check or set a password')
p.add_argument("user", type=email, help="User to login as")
p.add_argument("password", help="Password")
p.add_argument("--set", dest="setpassword", action="store_true", help="Set password")
p.set_defaults(func=password)

args = parser.parse_args()

logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO,
                    format='[%(asctime)s %(name)-12s %(levelname)-5s] %(message)s')

args.func(args)
