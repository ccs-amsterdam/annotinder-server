import bcrypt

from elasticsearch import Elasticsearch
es = Elasticsearch()

def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")

def _user_exists(email:str) -> bool:
    return es.exists(index=USERS, email= email)['_id']

def _check_annotations_index():
    """ check the annotation_index exists, create if not """
    if not es.indices.exists(INDEX):
        es.indices.create(INDEX)

def _check_annotations_users():
    """ check the annotation_users exists, create if not """
    if not es.indices.exists(USERS):
        es.indices.create(USERS)
        # add default admin user
        _add_user({'email': 'admin', 'role':'ADMIN', 'password':hash_password('admin'), 'id':1})

def _codingjob_exists(id: str) -> bool:
    return es.exists(index=INDEX, id=id)

def _create_codingjob(job: dict) -> str:
    return es.index(INDEX, job)['_id']

def _add_user(user: dict, field = '_id') -> str:
    return es.index(USERS, user)[field]

def _get_codingjob(id: str) -> dict:
    return es.get(INDEX, id=id)['_source']

def _get_user(email: str) -> dict:
    return es.get(USERS, email=email)

INDEX = "amcat4_annotations"
USERS = "annotations_users"
dummy_user = {'email': 'dummy', 'role':'CODER', 'password':hash_password('dummy')}