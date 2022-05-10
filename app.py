from flask import Flask

from db import db
from index import index_bp
from user import user_bp
from admin import admin_bp


def create_app(config):

    app = Flask(__name__)
    app.config['annotator'] = config
    app.secret_key = config['secret_key']
    # logger = get_logger(__name__, config)

    # db connection
    app.config['SQLALCHEMY_DATABASE_URI'] = config['db_url']
    # app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = True
    db.init_app(app)

    # https://realpython.com/flask-blueprint/
    app.register_blueprint(index_bp)
    app.register_blueprint(user_bp, url_prefix='/user')
    app.register_blueprint(admin_bp, url_prefix='/admin')

    return app
