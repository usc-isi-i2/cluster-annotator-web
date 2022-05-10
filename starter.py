import argparse
import json
import csv
import sys
import os

import utils
from db import *
from app import create_app


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Cluster Annotator')
    parser.add_argument('-c', '--config', dest='config_file', action='store', type=str, default='config.json')
    parser.add_argument('--init', dest='init', action='store_true')

    # create/update user
    # --create-user="{\"email\":\"test@test.org\"}"
    parser.add_argument('--create-user', dest='create_user', action='store', type=str)
    # create record, file_path must points to a csv file containing column id
    # --create-record="{\"file_path\":\"data/test_dataset.csv\"}"
    parser.add_argument('--create-record', dest='create_record', action='store', type=str)
    # create cluster
    # --create-cluster="{\"file_path\":\"data/test_cluster.json\"}"
    parser.add_argument('--create-cluster', dest='create_cluster', action='store', type=str)

    # run app
    parser.add_argument('-r', '--run-app', dest='run_app', action='store_true')
    args = parser.parse_args()

    config = utils.get_config(args.config_file)
    app = create_app(config)

    if args.init:
        with app.app_context():
            Meta.__table__.create(db.engine, checkfirst=True)
            Meta.set('mode', 'idle')
            sys.exit()

    if args.create_user:
        with app.app_context():
            User.__table__.create(db.engine, checkfirst=True)

            user_params = json.loads(args.create_user)
            if not user_params.get('email'):
                sys.exit('Invalid email.')
            user = User(email=user_params['email'],
                        password=user_params.get('password', None),
                        is_admin=user_params.get('admin', False))
            db.session.add(user)
            db.session.commit()
            sys.exit()

    if args.create_record:
        with app.app_context():
            record_params = json.loads(args.create_record)
            with open(record_params['file_path'], 'r', newline='') as csv_file:
                reader = csv.DictReader(csv_file)
                record_class_params = {'cols': reader.fieldnames}

                # save record class parameters
                meta = Meta(key='record_class_params', value=json.dumps(record_class_params))
                db.session.add(meta)
                db.session.commit()
                # with open(config['record_class_path'], 'w') as record_file:
                #     json.dump(record_class_params, record_file)

                # create record class
                Record = construct_record_class(**record_class_params)
                Record.__table__.create(db.engine, checkfirst=False)  # Force exception if exists

                # insert data
                for idx, row in enumerate(reader):
                    record = Record(**row)
                    db.session.add(record)
                    db.session.commit()

            sys.exit()

    if args.create_cluster:
        with app.app_context():
            Record = recover_record_class(Meta.get('record_class_params'))
            task_id = utils.gen_task_id()
            Cluster = construct_cluster_class(task_id)
            RecordClusterRelation = construct_cluster_record_relation_class(task_id)
            Cluster.__table__.create(db.engine, checkfirst=True)
            RecordClusterRelation.__table__.create(db.engine, checkfirst=True)
            Meta.set('task_id', task_id)

            cluster_params = json.loads(args.create_cluster)
            with open(cluster_params['file_path'], 'r') as json_file:
                clusters = json.load(json_file)

                for c in clusters:
                    cid = c['cid']
                    rids = c['rids']
                    cluster = Cluster(id=cid)
                    db.session.add(cluster)
                    for rid in rids:
                        rc_rel = RecordClusterRelation(rid=rid, cid=cid)
                        db.session.add(rc_rel)
                    db.session.commit()
            sys.exit()

    if args.run_app:
        with app.app_context():
            Record = recover_record_class(Meta.get('record_class_params'))
            Cluster = recover_cluster_class(Meta.get('task_id'))
            RecordClusterRelation = recover_cluster_record_relation_class(Meta.get('task_id'))
            bind_relationships(Record, Cluster, RecordClusterRelation)
            app.config['record_class'] = Record
            app.config['cluster_class'] = Cluster
            app.config['record_cluster_relation_class'] = RecordClusterRelation
        app.run(debug=config['debug'], host=config['host'], port=config['port'])
