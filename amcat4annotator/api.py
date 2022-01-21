import logging

from flask import Blueprint, request, abort, make_response, jsonify, g
from werkzeug.exceptions import HTTPException

from amcat4annotator import auth, rules
from amcat4annotator.db import create_codingjob, Unit, CodingJob, Annotation, User, STATUS, get_user_jobs, set_annotation
from amcat4annotator.auth import multi_auth, check_admin

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
      "rules": {
        "ruleset": <string>, .. additional options ..
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
    job = create_codingjob(title = job['title'], codebook=job['codebook'], provenance=job.get('provenance'),
                           rules=job['rules'], units=job['units'])
    return make_response(dict(id=job.id), 201)

@app_annotator.route("/login", methods=['GET'])
@multi_auth.login_required
def get_login():
    """
    All relevant information on login
    Currently: email, is_admin, (active) jobs, 
    """
    jobs = get_user_jobs(g.current_user.id)
    return jsonify({"jobs": jobs, "email": g.current_user.email, "is_admin": g.current_user.is_admin})

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


@app_annotator.route("/codingjob/<job_id>/codebook", methods=['GET'])
@multi_auth.login_required
def get_codebook(job_id):
    job = _job(job_id)
    return jsonify(job.codebook)


@app_annotator.route("/codingjob/<job_id>/progress", methods=['GET'])
@multi_auth.login_required
def progress(job_id):
    job = _job(job_id)
    return jsonify(rules.get_progress_report(job, g.current_user))


@app_annotator.route("/codingjob/<job_id>/unit", methods=['GET'])
@multi_auth.login_required
def get_unit(job_id):
    """
    Retrieve a single unit to be coded.
    If ?index=i is specified, seek a specific unit. Otherwise, return the next unit to code
    """
    job = _job(job_id)
    index = request.args.get("index")
    if index:
        u = rules.seek_unit(job, g.current_user, index=int(index))
    else:
        u = rules.get_next_unit(job, g.current_user)
    if not u:
        abort(404)
    result = {'id': u.id, 'unit': u.unit}
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


@app_annotator.route("/token", methods=['GET'])
@multi_auth.login_required
def get_token():
    """
    Get the token for the current
    If ?user=email@example.com is specified, get the token for that user (requires admin privilege)
    If &create=true is specified, create the user if it doesn't exist (otherwise returns 404)
    """
    user_email = request.args.get("user")
    if user_email:
        check_admin()
        user = User.get_or_none(User.email == user_email)
        print("\n???", user_email, user)
        if not user:
            if request.args.get("create", "").lower() == "true":
                user = User.create(email=user_email)
            else:
                abort(404)
    else:
        user = g.current_user
    return jsonify({"token": auth.get_token(user)})

