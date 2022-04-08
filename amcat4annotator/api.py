import hashlib
import logging


from flask import Blueprint, request, abort, make_response, jsonify, g
from werkzeug.exceptions import HTTPException, Unauthorized, NotFound

from amcat4annotator import auth, rules
from amcat4annotator.db import create_codingjob, Unit, CodingJob, Annotation, User, STATUS, get_user_jobs, \
    get_user_data, set_annotation, JobUser, add_jobusers
from amcat4annotator.auth import multi_auth, check_admin, check_job_user, get_jobtoken, verify_jobtoken

app_annotator = Blueprint('app_annotator', __name__)


@app_annotator.errorhandler(HTTPException)
def bad_request(e):
    logging.error(str(e))
    status = e.get_response(request.environ).status_code
    return jsonify(error=str(e)), status


def _job(job_id: int):
    job = CodingJob.get_or_none(CodingJob.id == job_id)
    if not job:
        abort(404)
    return job


@app_annotator.route("/codingjob", methods=['POST'])
@multi_auth.login_required
def create_job():
    """
    Create a new codingjob. Body should be json structured as follows:

     {
      "title": <string>,
      "codebook": {.. blob ..},
      "authorization": {  # optional, default: {'restricted': False}
        restricted: boolean,
        users: [emails]
      }
      "rules": {
        "ruleset": <string>,
        "authorization": "open"|"restricted",  # optional, default: open
        .. additional ruleset parameters ..
      },
      "units": [
        {"unit": {.. blob ..},
         "gold": {.. blob ..},  # optional, include correct answer here for gold questions
        }
        ..
      ],
      "provenance": {.. blob ..},  # optional
     }

    Where ..blob.. indicates that this is not processed by the backend, so can be annotator specific.
    See the annotator documentation for additional informations.

    The rules distribute how units should be distributed, how to deal with quality control, etc.
    The ruleset name specifies the class of rules to be used (currently "crowd" or "expert").
    Depending on the ruleset, additional options can be given.
    See the rules documentation for additional information
    """
    check_admin()
    job = request.get_json(force=True)
    if {"title", "codebook", "units", "rules"} - set(job.keys()):
        return make_response({"error": "Codinjob is missing keys"}, 400)
    job = create_codingjob(title=job['title'], codebook=job['codebook'], provenance=job.get('provenance'),
                           rules=job['rules'], units=job['units'], authorization=job.get('authorization'))
    return make_response(dict(id=job.id), 201)

@app_annotator.route("/codingjob/<job_id>/archived", methods=['GET'])
@multi_auth.login_required
def set_job_archived(job_id):
    """
    Toggle job.archived. Admin only. Archived jobs are no longer visible to coders.
    """
    check_admin()
    job = _job(job_id)
    job.archived = not job.archived
    job.save()
    return make_response(dict(archived=job.archived), 201)


@app_annotator.route("/codingjob/<job_id>/users", methods=['POST'])
@multi_auth.login_required
def add_job_users(job_id):
    """
    Add users to this coding job, creating them if they do not exist
    """
    check_admin()
    d = request.get_json(force=True)
    add_jobusers(codingjob_id=job_id, emails=d['users'])
    return make_response('', 204)


@app_annotator.route("/codingjob/<job_id>", methods=['GET'])
@multi_auth.login_required
def get_job(job_id):
    """
    Return a single coding job definition
    """
    check_admin()
    annotations = request.args.get("annotations")
    job = _job(job_id)
    units = list(Unit.select(Unit.id, Unit.gold, Unit.unit)
                     .where(Unit.codingjob==job).tuples().dicts().execute())
    cj = {
        "id": job_id,
        "title": job.title,
        "codebook": job.codebook,
        "provenance": job.provenance,
        "rules": job.rules,
        "units": units
    }
    if annotations:
        cj['annotations'] = list(Annotation.select(Annotation).join(Unit)
                 .where(Unit.codingjob==job).tuples().dicts().execute())
    return jsonify(cj)

@app_annotator.route("/codingjob/<job_id>/annotations", methods=['GET'])
@multi_auth.login_required
def get_job_annotations(job_id):
    """
    Return a single coding job definition
    """
    check_admin()
    job = _job(job_id)
    annotations = list(Annotation.select(Annotation).join(Unit).where(Unit.codingjob==job).tuples().dicts().execute())
    return jsonify(annotations)

@app_annotator.route("/codingjob/<job_id>/details", methods=['GET'])
@multi_auth.login_required
def get_job_details(job_id):
    """
    Return job details. Primarily for an admin to see progress and settings.
    """
    check_admin()
    annotations = request.args.get("annotations")
    job = _job(job_id)
    units = list(Unit.select(Unit.id, Unit.gold, Unit.unit)
                     .where(Unit.codingjob==job).tuples().dicts().execute())
    cj = {
        "title": job.title,
        "codebook": job.codebook,
        "provenance": job.provenance,
        "rules": job.rules,
        "units": units
    }
    if annotations:
        cj['annotations'] = list(Annotation.select(Annotation).join(Unit)
                 .where(Unit.codingjob==job).tuples().dicts().execute())
    return jsonify(cj)




@app_annotator.route("/codingjob/<job_id>/token", methods=['GET'])
@multi_auth.login_required
def get_job_token(job_id):
    """
    Create a 'job token' for this job
    This allows anyone to code units on this job
    """
    check_admin()
    job = _job(job_id)
    token = get_jobtoken(job)
    return jsonify({"token": token})


@app_annotator.route("/jobtoken", methods=['GET'])
def redeem_job_token():
    """
    Convert a job token into a 'normal' token.
    Should be called with a token and optional user_id argument
    """
    token = request.args['token']
    job = verify_jobtoken(token)
    if not job:
        raise Unauthorized("Job token not valid")
    user_id = request.args.get('user_id')
    if not user_id:
        x = hashlib.sha1()
        x.update(str(User.select().count()).encode('utf-8'))
        user_id = x.hexdigest()
    email = f"jobuser__{job.id}__{user_id}"
    user = User.get_or_none(User.email == email)
    if not user:
        user = User.create(email=email)
    return jsonify({"token": auth.get_token(user),
                    "email": user.email,
                    "is_admin": user.is_admin})


@app_annotator.route("/codingjob/<job_id>/codebook", methods=['GET'])
@multi_auth.login_required
def get_codebook(job_id):
    job = _job(job_id)
    check_job_user(job)
    return jsonify(job.codebook)


@app_annotator.route("/codingjob/<job_id>/progress", methods=['GET'])
@multi_auth.login_required
def progress(job_id):
    job = _job(job_id)
    check_job_user(job)
    return jsonify(rules.get_progress_report(job, g.current_user))


@app_annotator.route("/codingjob/<job_id>/unit", methods=['GET'])
@multi_auth.login_required
def get_unit(job_id):
    """
    Retrieve a single unit to be coded.
    If ?index=i is specified, seek a specific unit. Otherwise, return the next unit to code
    """
    job = _job(job_id)
    check_job_user(job)
    index = request.args.get("index")
    if index:
        index = int(index)
        u = rules.seek_unit(job, g.current_user, index=index)
    else:
        u, index = rules.get_next_unit(job, g.current_user)
    if not u:
        abort(404)
    result = {'id': u.id, 'unit': u.unit, 'index': index}
    a = list(Annotation.select().where(Annotation.unit == u.id, Annotation.coder == g.current_user.id))
    if a:
        result['annotation'] = a[0].annotation
        result['status'] = a[0].status
    return jsonify(result)


@app_annotator.route("/codingjob/<job_id>/unit/<unit_id>/annotation", methods=['POST'])
@multi_auth.login_required
def post_annotation(job_id, unit_id):
    """
    Set the annotations for a specific unit
    POST body should consist of a json object:
    {
      "annotation": {..blob..},
      "status": "DONE"|"IN_PROGRESS"|"SKIPPED"  # optional
    }
    """
    # TODO check if this coder is allowed to set this annotation
    unit = Unit.get_or_none(Unit.id == unit_id)
    job = _job(job_id)
    check_job_user(job)
    if not unit:
        abort(404)
    if unit.codingjob != job:
        abort(400)
    body = request.get_json(force=True)
    if not body:
        abort(400)
    if not 'annotation' in body:
        abort(400)
    annotation = body.get('annotation')
    status = body.get('status')
    set_annotation(unit.id, coder=g.current_user.email, annotation=annotation, status=status)
    return make_response('', 204)


@app_annotator.route("/users/me/token", methods=['GET'])
@multi_auth.login_required
def get_my_token():
    """
    Get the token (and user details) for the current user
    """
    return jsonify({"token": auth.get_token(g.current_user),
                    "email": g.current_user.email,
                    "is_admin": g.current_user.is_admin})


@app_annotator.route("/users/me/codingjobs", methods=['GET'])
@multi_auth.login_required
def get_my_jobs():
    """
    Get a list of coding jobs
    Currently: email, is_admin, (active) jobs,
    """
    jobs = get_user_jobs(g.current_user.id)
    return jsonify({"jobs": jobs})


@app_annotator.route("/users/<email>/token", methods=['GET'])
@multi_auth.login_required
def get_user_token(email):
    """
    Get the  token for the given user
    """
    check_admin()
    try:
        user = User.get(User.email == email)
    except User.DoesNotExist:
        raise NotFound()
    return jsonify({"token": auth.get_token(user)})


@app_annotator.route("/users", methods=['GET'])
@multi_auth.login_required
def get_users():
    """
    Get a list of all users
    """
    check_admin()
    users = get_user_data()
    return jsonify({"users": users})


@app_annotator.route("/users", methods=['POST'])
@multi_auth.login_required
def add_users():
    check_admin()
    body = request.get_json(force=True)

    if 'users' not in body.keys():
        return make_response({"error": "Body needs to have users"}, 400)
    for user in body['users']:
        u = User.get_or_none(User.email == user['email'])
        if u:
            continue
        password = auth.hash_password(user['password']) if user['password'] else None
        u = User.create(email=user['email'], is_admin=user['admin'], password=password)
    return make_response('', 204)


@app_annotator.route("/password", methods=['POST'])
@multi_auth.login_required
def set_password():
    body = request.get_json(force=True)

    if 'password' not in body.keys():
        return make_response({"error": "Body needs to have password"}, 400)

    if 'email' in body.keys():
        if body['email'] != g.current_user.id:
            check_admin()
        user = User.get(User.email == body['email'])
    else:
        user = User.get(User.email == g.current_user.id)

    user.password = auth.hash_password(body['password'])
    user.save()
    return make_response('', 204)

# TODO
# - redeem_jobtoken moet user kunnen creeren vor een 'job token' (en email/id teruggeven) [untested]
# - endpoint om 'job tokens' te kunnen aanmaken [untested]
