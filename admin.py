from collections import defaultdict
from functools import wraps
import json

from flask import Blueprint, render_template, request, redirect, url_for, session
from flask import current_app as app
import flask_login

import utils
from db import *


login_manager = flask_login.LoginManager()


admin_bp = Blueprint('admin_bp', __name__)


def admin_required(func):
    @wraps(func)
    @flask_login.login_required  # login first
    def decorated_func(*args, **kwargs):
        if not flask_login.current_user.is_admin:
            return 'Not Authorized', 401
        return func(*args, **kwargs)
    return decorated_func


@admin_bp.route('/')
@admin_required
def admin():
    args = request.args.to_dict()
    message = {}
    if args.get('message'):
        message = json.loads(args['message'])

    data = {
        'user': {'email': flask_login.current_user.email, 'is_admin': flask_login.current_user.is_admin},
        'mode': Meta.get('mode'),
        'users': User.query.with_entities(User.id, User.email, User.is_admin).order_by(User.id).all()
    }

    return render_template('admin.html', data=data, message=message)


@admin_bp.route('/generate', methods=['POST'])
@admin_required
def generate():
    message = {}

    _ = request.form.to_dict()

    # generate annotation
    Record = app.config['record_class']
    Cluster = app.config['cluster_class']
    RecordClusterRelation = app.config['record_cluster_relation_class']

    record_to_cluster = {}
    mode = Meta.get('mode')
    for rel in RecordClusterRelation.query.all():
        record_to_cluster[rel.rid] = utils.gen_new_cid(rel.cid, rel.new_cid, mode)
    cluster_to_record = defaultdict(list)
    for rid, cid in record_to_cluster.items():
        cluster_to_record[cid].append(rid)
    clusters = []
    for cid, rids in cluster_to_record.items():
        clusters.append({'rids': rids, 'cid': cid})

    # save meta state for reverse in case
    prev_mode = Meta.get('mode')
    prev_task_id = Meta.get('task_id')
    try:
        task_id = utils.gen_task_id()

        # change meta
        Meta.set('mode', 'idle')
        Meta.set('task_id', task_id)

        # create new cluster and relation
        del Cluster
        del RecordClusterRelation
        Cluster = construct_cluster_class(task_id)
        RecordClusterRelation = construct_cluster_record_relation_class(task_id)
        Cluster.__table__.create(db.engine, checkfirst=True)
        RecordClusterRelation.__table__.create(db.engine, checkfirst=True)
        bind_relationships(Record, Cluster, RecordClusterRelation)
        app.config['cluster_class'] = Cluster
        app.config['record_cluster_relation_class'] = RecordClusterRelation

        for c in clusters:
            cid = c['cid']
            rids = c['rids']
            cluster = Cluster(id=cid)
            db.session.add(cluster)
            for rid in rids:
                rc_rel = RecordClusterRelation(rid=rid, cid=cid)
                db.session.add(rc_rel)
            db.session.commit()

    except Exception as e:
        # change meta
        Meta.set('mode', prev_mode)
        Meta.set('task_id', prev_task_id)

        try:
            del RecordClusterRelation
        except:
            pass
        try:
            del Cluster
        except:
            pass

        Cluster = construct_cluster_class(prev_task_id)
        RecordClusterRelation = construct_cluster_record_relation_class(prev_task_id)
        bind_relationships(Record, Cluster, RecordClusterRelation)
        app.config['cluster_class'] = Cluster
        app.config['record_cluster_relation_class'] = RecordClusterRelation

        message['error'] = f'Failed to apply annotations.\n{e}'

    return redirect(url_for('admin_bp.admin', message=json.dumps(message)))


@admin_bp.route('/discard', methods=['POST'])
@admin_required
def discard():
    message = {}

    _ = request.form.to_dict()

    Record = app.config['record_class']
    Cluster = app.config['cluster_class']
    RecordClusterRelation = app.config['record_cluster_relation_class']

    for c in Cluster.query.all():
        c.annotation = None
        c.annotated_by = None
        c.annotated_at = None
    for rel in RecordClusterRelation.query.all():
        rel.new_cid = None

    db.session.commit()

    return redirect(url_for('admin_bp.admin'))


@admin_bp.route('/mode', methods=['POST'])
@admin_required
def mode():
    params = request.form.to_dict()
    mode = params['mode'].strip().lower()
    Meta.set('mode', mode)

    return redirect(url_for('admin_bp.admin'))
