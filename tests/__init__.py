import logging

from amcat4annotator import db

def setup_package():
    logging.warning("Setting up!")
    db.initialize_if_needed()
