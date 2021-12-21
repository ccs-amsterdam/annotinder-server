from flask import Blueprint, request, abort, make_response, jsonify

from amcat4annotator.db import create_codingjob, Unit, CodingJob

app_annotator = Blueprint('app_annotator', __name__)

from amcat4annotator.annotation_auth import multi_auth

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
    job = request.get_json(force=True)
    if {"title", "codebook", "units", "rules"} - set(job.keys()):
        return make_response({"error": "Codinjob is missing keys"}, 400)
    job = create_codingjob(codebook=job['codebook'], provenance=job.get('provenance'),
                           rules=job['rules'], units=job['unts'])
    return make_response(dict(id=job.id), 201)


@app_annotator.route("/codingjob/<id>", methods=['GET'])
@multi_auth.login_required
def get_job(id):
    """
    Return a single coding job definition
    """
    job = CodingJob.get_or_none(CodingJob.id == id)
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


@app_annotator.route("/token/", methods=['GET'])
#@multi_auth.login_required
def get_token(expiration: int = None):
    #s = TimedJSONWebSignatureSerializer(SECRET_KEY, expires_in=expiration)
    #g.current_user['token'] = s.dumps({'email': g.current_user['email']})
    #return jsonify({"token": g.current_user['token'].decode('ascii')})
    return jsonify({"token": "hetbadisbestgroot"})


@app_annotator.route("/codingjob/<id>/codebook", methods=['GET'])
@multi_auth.login_required
def get_codebook(id):
    job = _get_codingjob(id)
    return job['codebook']


@app_annotator.route("/codingjob/<id>/unit", methods=['GET'])
@multi_auth.login_required
def get_next_unit(id):
    """
    Retrieve a single unit to be coded. Currently, the next uncoded unit
    """
    #TODO: authenticate the user (e.g. using bearer token)
    user = request.args.get('user')
    if not user:
        abort(401)
    job = _get_codingjob(id)
    best = None  # (i, min_n_coded, unit)
    for i, unit in enumerate(job['units']):
        coders = set([annotation['user'] for annotation in unit.get("annotations", [])])
        # coders = set(unit.get("annotations", []).keys())
        if user not in coders:
            if best is None or len(coders) < best[0]:
                best = len(coders), i, unit
    if best:
        return {'id': best[1], 'unit': best[2]}
    abort(404)

@app_annotator.route("/codingjob/<job_id>/unit/<unit_id>/annotation", methods=['POST'])
# @multi_auth.login_required
def set_annotation(job_id, unit_id):
    """Set the annotations for a specific unit"""
    #TODO: authenticate the user (e.g. using bearer token)
    user = request.args.get('user')
    if not user:
        abort(401)
    job = _get_codingjob(job_id)
    annotations = request.get_json(force=True)
    try:
        unit = job["units"][int(unit_id)]
    except (ValueError, IndexError):
        abort(404)  # unit did not exist or was not integer
    if "annotations" not in unit:
        unit["annotations"] = []

    # finding the list of coders
    coders = set([annotation['user'] for annotation in unit.get("annotations", [])])
    if user not in coders: # if this is the first time the user comes in
        unit["annotations"].append({'user': user, 'annotation': annotations})
    elif user  in coders:
        for item in unit["annotations"]:
            if (item['user'] == user):
                item.update({"annotation": annotations}) # updating the annotation of that user
    es.index(INDEX, id=job_id, body=job)
    return make_response('', 204)
