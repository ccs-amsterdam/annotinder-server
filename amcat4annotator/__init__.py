from flask import Flask

from amcat4annotator.api import app_annotator

api = Flask(__name__)
api.register_blueprint(app_annotator)