import logging

from flask import Blueprint, request, abort, make_response, jsonify, g
from werkzeug.exceptions import HTTPException

from amcat4annotator import auth
from amcat4annotator.db import create_codingjob, Unit, CodingJob
from amcat4annotator.auth import multi_auth, check_admin

app_annotator = Blueprint('app_annotator', __name__)


@app_annotator.errorhandler(HTTPException)
def bad_request(e):
    logging.error(str(e))
    status = e.get_response(request.environ).status_code
    return jsonify(error=str(e)), status


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


@app_annotator.route("/codingjob/<job_id>", methods=['GET'])
@multi_auth.login_required
def get_job(job_id):
    """
    Return a single coding job definition
    """
    check_admin()
    job = CodingJob.get_or_none(CodingJob.id == job_id)
    if not job:
        abort(404)
    units = (Unit.select(Unit.id, Unit.gold, Unit.status, Unit.unit, Unit.status)
             .where(Unit.codingjob==job).tuples().dicts())
    return jsonify({
        "title": job.title,
        "codebook": job.codebook,
        "provenance": job.provenance,
        "rules": job.rules,
        "units": units
    })


@app_annotator.route("/codingjob/<job_id>/codebook", methods=['GET'])
@multi_auth.login_required
def get_codebook(job_id):
    job = CodingJob.get_or_none(CodingJob.id == job_id)
    if not job:
        abort(404)
    return jsonify(job.codebook)


@app_annotator.route("/codingjob/<job_id>/progress", methods=['GET'])
@multi_auth.login_required
def progress(job_id):
    job = CodingJob.get_or_none(CodingJob.id == job_id)
    if not job:
        abort(404)
    return jsonify({
        'n_coded': 0,
        'n_total': 100,
        'seek_backwards': True,
        'seek_forwards': False,
    })


@app_annotator.route("/codingjob/<id>/unit", methods=['GET'])
@multi_auth.login_required
def get_next_unit(id):
    """
    Retrieve a single unit to be coded. Currently, the next uncoded unit
    """
    #TODO: authenticate the user (e.g. using bearer token)
    #TODO: implement rules
    job = CodingJob.get_or_none(CodingJob.id == id)
    if not job:
        abort(404)
    units = (Unit.select(Unit.id, Unit.gold, Unit.status, Unit.unit, Unit.status)
             .where(Unit.codingjob == job).tuples().dicts())
    return jsonify({'id': -1, 'unit': units[0]})


@app_annotator.route("/codingjob/<job_id>/unit/<index>", methods=['GET'])
@multi_auth.login_required
def get_unit(job_id, index):
    job = CodingJob.get_or_none(CodingJob.id == job_id)
    if not job:
        abort(404)
    units = (Unit.select(Unit.id, Unit.gold, Unit.status, Unit.unit, Unit.status)
             .where(Unit.codingjob == job).tuples().dicts())
    return jsonify({'id': -1, 'unit': units[0]})


@app_annotator.route("/codingjob/<job_id>/unit/<unit_id>/annotation", methods=['POST'])
@multi_auth.login_required
def set_annotation(job_id, unit_id):
    """Set the annotations for a specific unit"""
    #TODO: authenticate the user (e.g. using bearer token)
    return make_response('', 204)


@app_annotator.route("/token", methods=['GET'])
@multi_auth.login_required
def get_token():
    return jsonify({"token": auth.get_token(g.current_user)})
