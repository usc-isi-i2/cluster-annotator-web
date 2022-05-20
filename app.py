from werkzeug.middleware.dispatcher import DispatcherMiddleware
from werkzeug.wrappers import Response
from flask import Flask, request

from db import db
from index import index_bp
from user import user_bp
from admin import admin_bp


def create_app(config):

    app = Flask(__name__)
    app.config['annotator'] = config
    app.secret_key = config['secret_key']

    # base url
    base_url = app.config['annotator'].get('base_url', '')
    app.wsgi_app = DispatcherMiddleware(
        Response('Not Found', status=404),
        {base_url: app.wsgi_app}
    )
    # logger = get_logger(__name__, config)

    # db connection
    app.config['SQLALCHEMY_DATABASE_URI'] = config['db_url']
    # app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = True
    db.init_app(app)

    # https://realpython.com/flask-blueprint/
    app.register_blueprint(index_bp)
    app.register_blueprint(user_bp, url_prefix='/user')
    app.register_blueprint(admin_bp, url_prefix='/admin')

    @app.context_processor
    def inject_context():
        return dict(APP_NAME=app.config['annotator'].get('title', 'Cluster Annotator'), BASE_URL=request.script_root)

    return app
