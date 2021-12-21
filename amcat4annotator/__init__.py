from flask import Flask
from flask_cors import CORS

from amcat4annotator.api import app_annotator

app = Flask(__name__)
CORS(app)
app.register_blueprint(app_annotator)
