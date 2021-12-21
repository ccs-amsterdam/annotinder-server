from flask import Flask
from flask_cors import CORS

from amcat4annotator.api import app_annotator

api = Flask(__name__)
CORS(api)
api.register_blueprint(app_annotator)