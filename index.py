from datetime import datetime, timezone
from collections import defaultdict

from flask import Blueprint, render_template, request, redirect, url_for, session, jsonify
from flask import current_app as app
import flask_login
from sqlalchemy import func

from db import *
import utils

login_manager = flask_login.LoginManager()
index_bp = Blueprint('index_bp', __name__)


@index_bp.route('/ping')
def ping():
    return 'pong'


@index_bp.route('/')
@flask_login.login_required
def home():
    Record = app.config['record_class']
    Cluster = app.config['cluster_class']
    RecordClusterRelation = app.config['record_cluster_relation_class']

    data = {
        'user': {'email': flask_login.current_user.email, 'is_admin': flask_login.current_user.is_admin},
        'mode': Meta.get('mode'),
        'stat': {
            'num_of_clusters': Cluster.query.count(),
            'num_of_annotated_clusters': Cluster.query.filter(Cluster.annotation != None).count(),
            'num_of_annotated_clusters_by_user': Cluster.query.filter(
                Cluster.annotated_by == flask_login.current_user.id).count(),
            'num_of_remaining_clusters': Cluster.query.filter(Cluster.annotation == None).count()
        }
    }
    return render_template('home.html', message={}, data=data)


@index_bp.route('/progress')
@flask_login.login_required
def progress():
    Record = app.config['record_class']
    Cluster = app.config['cluster_class']
    RecordClusterRelation = app.config['record_cluster_relation_class']

    message = {}
    args = request.args.to_dict()

    view = args.get('view')
    if view == 'records':
        import json
        cols = json.loads(Meta.get('record_class_params'))['cols']

        # records = {}
        # for r in Record.query.all():
        #     records[r.id] = {c: getattr(r, c) for c in cols}
        #     records[r.id]['cid'] = r.relations[0].cid
        #     records[r.id]['new_cid'] = r.relations[0].new_cid

        data = {
            'mode': Meta.get('mode'),
            'records': [],  # records,
            'data_columns': cols + ['cid', 'new_cid'],
            'user': {'email': flask_login.current_user.email, 'is_admin': flask_login.current_user.is_admin},
        }
    else:  # cluster view by default

        # clusters = {c.id: {'name': c.records[0], 'size': len(c.relations), 'status': c.annotation}
        #             for c in Cluster.query.all()}

        data = {
            'mode': Meta.get('mode'),
            'clusters': [],  # clusters,
            'user': {'email': flask_login.current_user.email, 'is_admin': flask_login.current_user.is_admin},

        }

    return render_template('progress.html', data=data, message=message)


@index_bp.route('/progress/data')
@flask_login.login_required
def progress_data():
    Record = app.config['record_class']
    Cluster = app.config['cluster_class']
    RecordClusterRelation = app.config['record_cluster_relation_class']

    args = request.args.to_dict()

    view = args.get('view')
    limit = args.get('limit', 10)
    offset = args.get('offset', 0)
    # sort = args.get('sort')
    # order = args.get('order')
    # search = args.get('search')

    if view == 'records':
        total_count = Record.query.count()

        import json
        cols = json.loads(Meta.get('record_class_params'))['cols']
        records = []
        for r in Record.query.offset(offset).limit(limit).all():
            rr = {c: getattr(r, c) for c in cols}
            rr['cid'] = r.relations[0].cid
            if Meta.get('mode') == 'split':
                if r.relations[0].new_cid:
                    rr['new_cid'] = utils.gen_new_cid(r.relations[0].cid, r.relations[0].new_cid)
                else:
                    rr['new_cid'] = ''
            else:
                rr['new_cid'] = r.relations[0].new_cid
            records.append(rr)

        json_ret = {
            'total': total_count,
            'totalNotFiltered': total_count,
            'rows': records
        }
    else:
        total_count = Cluster.query.count()

        def convert_status(s):
            return {
                CLUSTER_ANNOTATION_NULL: '',
                CLUSTER_ANNOTATION_ANNOTATED: 'Annotated',
                CLUSTER_ANNOTATION_IGNORED: 'Ignored'
            }[s]

        clusters = [{'id': c.id,
                     'name': str(c.records[0]),
                     'size': len(c.relations),
                     'status': convert_status(c.annotation),
                     'by': User.query.get(c.annotated_by).email if c.annotated_by else ''}
                    for c in Cluster.query.offset(offset).limit(limit).all()]

        json_ret = {
            'total': total_count,
            'totalNotFiltered': total_count,
            'rows': clusters
        }

    return jsonify(json_ret)


@index_bp.route('/annotation')
@flask_login.login_required
def annotation():
    Record = app.config['record_class']
    Cluster = app.config['cluster_class']
    RecordClusterRelation = app.config['record_cluster_relation_class']

    message = {}
    args = request.args.to_dict()

    data = {
        'mode': Meta.get('mode'),
        'user': {'email': flask_login.current_user.email, 'is_admin': flask_login.current_user.is_admin},
    }

    try:
        if 'search' in args:
            query_text = args['query'].strip()
            # query_text = query_text.replace(' ', '+')
            if not query_text:
                results = Cluster.query.filter(Cluster.annotation == None).order_by(func.random()).limit(10).all()
                clusters = {c.id: {'name': c.records[0], 'size': len(c.relations)} for c in results}
            else:
                results = db.session.query(Cluster, func.count(Record.id))\
                    .join(RecordClusterRelation, Cluster.id == RecordClusterRelation.cid)\
                    .join(Record, RecordClusterRelation.rid == Record.id) \
                    .filter(Record.__ts_vec__.match(query_text))\
                    .filter(Cluster.annotation == None)\
                    .group_by(Cluster.id).limit(10).all()  # .all().distinct(Cluster.id)
                clusters = {c.id: {'name': c.records[0], 'size': len(c.relations), 'hits': cnt} for c, cnt in results}
            data['clusters'] = clusters
    except Exception as e:
        message['error'] = f'Invalid parameters.\n{e}'

    return render_template('annotation.html', data=data, message=message)


@index_bp.route('/annotation/split/<cluster_id>', methods=['GET', 'POST'])
@flask_login.login_required
def split(cluster_id):
    Record = app.config['record_class']
    Cluster = app.config['cluster_class']
    RecordClusterRelation = app.config['record_cluster_relation_class']

    message = {}
    data = {'cluster_id': cluster_id}

    if request.method == 'POST':
        # form validation
        for rid, new_cid in request.form.to_dict().items():
            new_cid = new_cid.strip()
            if not new_cid.isnumeric():
                message['error'] = 'Invalid cluster id assigned.'
                break

        # write to database
        cluster = Cluster.query.get(cluster_id)

        # race condition: check if the cluster has already been annotated by somebody else
        # if cluster.annotation != None and cluster.annotated_by != flask_login.current_user.id:
        #     message['error'] = 'This cluster has been annotated by another annotator.'
        # else:

        # update the cluster to be annotated
        cluster.annotation = CLUSTER_ANNOTATION_ANNOTATED
        cluster.annotated_by = flask_login.current_user.id
        cluster.annotated_at = datetime.now(timezone.utc)

        # update on records
        for rid, new_cid in request.form.to_dict().items():
            new_cid = new_cid.strip()

            rid = rid[4:]
            # update relation
            relation = RecordClusterRelation.query.filter_by(cid=cluster_id, rid=rid).first()
            relation.new_cid = new_cid

        # submit
        db.session.commit()

    import json
    cols = json.loads(Meta.get('record_class_params'))['cols']
    data['data_columns'] = cols
    data['cluster_name'] = Cluster.query.get(cluster_id).records[0]

    records = {}
    for r in Cluster.query.get(cluster_id).records:
        records[r.id] = {c: getattr(r, c) for c in cols}
        records[r.id]['new_cid'] = r.relations[0].new_cid or 0
    data['records'] = records

    status_code = 200 if 'error' not in message else 400
    return render_template('split.html', data=data, message=message), status_code


# @index_bp.route('/annotation/merge/<cluster_id>', methods=['GET', 'POST'])
# @flask_login.login_required
# def merge(cluster_id):
#     message = {}
#     data = {'cluster_id': cluster_id}
#
#     Record = app.config['record_class']
#     import json
#     cols = json.loads(Meta.get('record_class_params'))['cols']
#     data['data_columns'] = cols
#     data['cluster_name'] = Cluster.query.get(cluster_id).records[0]
#
#     return render_template('merge.html', data=data, message=message)


# @index_bp.route('/annotation/search')
# @flask_login.login_required
# def search():
#     Record = app.config['record_class']
#     Cluster = app.config['cluster_class']
#     RecordClusterRelation = app.config['record_cluster_relation_class']
#
#     message = {}
#     data = {}
#     args = request.args.to_dict()
#
#     if 'search' in args:
#         query_text = args['query'].strip()
#         results = db.session.query(Cluster, func.count(Record.id)) \
#             .join(RecordClusterRelation, Cluster.id == RecordClusterRelation.cid) \
#             .join(Record, RecordClusterRelation.rid == Record.id) \
#             .filter(Record.__ts_vec__.match(query_text)) \
#             .filter(Cluster.annotation == None) \
#             .group_by(Cluster.id).limit(10).all()
#         clusters = {c.id: {'name': c.records[0], 'size': len(c.relations), 'hits': cnt} for c, cnt in results}
#         data['clusters'] = clusters
#
#     # return render_template('merge.html', data=data, message=message)
#     return ''
