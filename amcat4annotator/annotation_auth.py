import os, json, time
import logging
from flask import Blueprint, g, request, jsonify
from flask_httpauth import HTTPBasicAuth, HTTPTokenAuth, MultiAuth
import bcrypt
from amcat4annotator.common import _get_codingjob, _add_user, hash_password, _user_exists
from itsdangerous import TimedJSONWebSignatureSerializer, SignatureExpired, BadSignature
from urllib.parse import urlparse

app_annotator_auth = Blueprint('app_annotator_auth', __name__)

from elasticsearch import Elasticsearch
es = Elasticsearch()

basic_auth = HTTPBasicAuth()
token_auth = HTTPTokenAuth()
multi_auth = MultiAuth(basic_auth, token_auth)

USERS = "annotations_users"
SECRET_KEY = "NOT VERY SECRET YET!"
CODING_JOB_TYPE = ["CROWD","EXPERT","PANEL"]
AUTHENTICATION = ["NONE","USERNAME","USER_PASS","TOKEN"]
AUTHORIZATION = ["ANY","NEXT_UNCODED","SPECIFIED"]

@basic_auth.verify_password
def verify_password(username, password):
    if (not username):
        username = request.args.get('user')

    g.current_user = _check_auth_method(request.args.get('id'), username, password)
    return g.current_user is not None

@token_auth.verify_token
def verify_token(token):
    g.current_user = _verify_token(token)
    return g.current_user is not None

def _verify_user(email: str, password: str) -> bool:
    """
    Check that this user exists and can be authenticated with the given password, returning a User object
    :param email: Email address identifying the user
    :param password: Password to check
    :return: A User object if user could be authenticated, None otherwise
    """
    logging.info("Attempted login (user+pass): {email}".format(**locals()))
    try:
        user = _get_user(email)
    except:
        logging.warning("User {email} not found!".format(**locals()))
        return None
    if bcrypt.checkpw(password.encode('utf-8'), user['password'].encode("utf-8")):
        return user
    else:
        logging.warning("Incorrect password for user {email}".format(**locals()))

def _get_user(e,field = 'email'):
    search_object = {'query': {'match': {field: e}}}
    result = es.search(index=USERS, body=json.dumps(search_object))
    user = [dict(_id=hit['_id'], **hit['_source']) for hit in result['hits']['hits']][0]
    return(user)

@app_annotator_auth.route("/anno/auth/token/", methods=['GET'])
@multi_auth.login_required
def get_token(expiration: int = None):
    s = TimedJSONWebSignatureSerializer(SECRET_KEY, expires_in=expiration)
    g.current_user['token'] = s.dumps({'email': g.current_user['email']})
    return jsonify({"token": g.current_user['token'].decode('ascii')})

def _verify_token(token):
    """
        Check the token and return the authenticated user email
        :param token: The token to verify
        :return: a User object if user could be authenticated, None otherwise
        """
    s = TimedJSONWebSignatureSerializer(SECRET_KEY)
    try:
        result = s.loads(token)
    except (SignatureExpired, BadSignature):
        logging.exception("Token verification failed")
        return None
    logging.warning("TOKEN RESULT: {}".format(result))
    return _get_user(result['email'],'email')


def _check_auth_method(codingjobId, username, password = None, token = None):
    if (codingjobId == None):
        # server level authentication needs user and pass
        return _verify_user(username, password)

    rules = _get_codingjob(codingjobId)['rules']
    if (rules['authentication']=='user'):
        try:
            return _get_user(username)
        except:
            newUser = {'email': username, 'role': 'CODER', 'password': hash_password(username)}
            _add_user(newUser)
            time.sleep(1)
            return newUser
    elif (rules['authentication']=='user_pass'):
        return _verify_user(username,password)
    elif (rules['authentication']=='token'):
        return _verify_token(token)
    return None