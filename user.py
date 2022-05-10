import base64

from flask import Blueprint, render_template, request, redirect, url_for, session
from flask import current_app as app
import flask_login
from captcha.image import ImageCaptcha

import utils
from db import db, User


login_manager = flask_login.LoginManager()


user_bp = Blueprint('user_bp', __name__)


@login_manager.user_loader
def user_loader(id):
    return User.query.get(id)


@login_manager.unauthorized_handler
def unauthorized_handler():
    return redirect(url_for('user_bp.login'))


@user_bp.record_once
def on_load(state):
    login_manager.init_app(state.app)


def gen_captcha():
    captcha_gen = ImageCaptcha(width=120, height=50, font_sizes=(30, 35, 40, 45))
    captcha_str = utils.gen_random_string(length=4).upper()
    captcha_img = captcha_gen.generate(captcha_str)
    captcha_img = base64.b64encode(captcha_img.read()).decode('utf-8')
    return captcha_str, captcha_img


@user_bp.route('/login', methods=['GET', 'POST'])
def login():
    message = {}

    if request.method == 'POST':

        email = request.form['email']
        password = request.form['password']
        captcha = request.form['captcha']

        if app.config['annotator']['debug'] or session.get('captcha') == captcha:  # bypass CAPTCHA in debug mode
            user = User.query.filter_by(email=email, password=password).first()
            if user:
                user.authenticated = True
                db.session.add(user)
                db.session.commit()
                session.pop('captcha')
                flask_login.login_user(user)
                return redirect(url_for('index_bp.home'))

        message['error'] = 'Incorrect input, please re-enter!'

    # already logged in
    if flask_login.current_user.is_authenticated:
        return redirect(url_for('index_bp.home'))

    # prepare for login
    captcha_str, captcha_img = gen_captcha()
    session['captcha'] = captcha_str
    return render_template('login.html', message=message, data={'captcha': captcha_img})


@user_bp.route('/logout')
def logout():
    user = flask_login.current_user
    user.authenticated = False
    db.session.add(user)
    db.session.commit()
    flask_login.logout_user()
    return redirect(url_for('user_bp.login'))
