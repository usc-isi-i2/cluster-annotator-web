import os.path
import random
import time

import sqlalchemy
from sqlalchemy.dialects.postgresql import TSVECTOR
from sqlalchemy.ext.hybrid import hybrid_property, hybrid_method
from flask_sqlalchemy import SQLAlchemy
import flask_login

import utils


db = SQLAlchemy()


# https://flask-login.readthedocs.io/en/latest/_modules/flask_login/mixins/#UserMixin
# https://realpython.com/using-flask-login-for-user-management-with-flask/#the-user-model
class User(db.Model, flask_login.UserMixin):
    __tablename__ = 'user'

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    email = db.Column(db.String, unique=True)
    password = db.Column(db.String, nullable=False)
    is_admin = db.Column(db.Boolean, default=False)

    def __init__(self, email, password=None, is_admin=False):
        self.email = email
        self.password = password or utils.gen_random_string(length=10)
        self.is_admin = is_admin

    def __repr__(self):
        return f'<User {self.email} (is_admin={self.is_admin})>'

    def is_active(self):
        """True, as all users are active."""
        return True

    def get_id(self):
        return self.id

    def get_email(self):
        """Return the email address to satisfy Flask-Login's requirements."""
        return self.email

    def is_authenticated(self):
        """Return True if the user is authenticated."""
        return self.authenticated

    def is_anonymous(self):
        """False, as anonymous users aren't supported."""
        return False


# def update_user(email, password=None, is_admin=None):
#     # None means keeping the property as it was
#     user = User.query.filter_by(email=email).first()
#     if user:  # update user
#         if is_admin is not None:
#             user.is_admin = is_admin
#         if password:
#             user.password = password
#         db.session.commit()
#     else:  # create user
#         user = User(email=email, is_admin=is_admin, password=password)
#         db.session.add(user)
#         db.session.commit()


# https://blog.crunchydata.com/blog/postgres-full-text-search-a-search-engine-in-a-database
# https://amitosh.medium.com/full-text-search-fts-with-postgresql-and-sqlalchemy-edc436330a0c
class TSVector(sqlalchemy.types.TypeDecorator):
    impl = TSVECTOR

# Full text search
# https://leandronsp.com/a-powerful-full-text-search-in-postgresql-in-less-than-20-lines
# Fuzzy search
# https://stackoverflow.com/questions/2513501/postgresql-full-text-search-how-to-search-partial-words
# SELECT *
# FROM record
# --WHERE address LIKE '%BLV%' and address LIKE '%3800%'
# WHERE __ts_vec__ @@ to_tsquery('english', 'BLV:* & 3800')

# dynamic table
# https://sparrigan.github.io/sql/sqla/2016/01/03/dynamic-tables.html
# https://github.com/sqlalchemy/sqlalchemy/discussions/7289
# record class is dynamically created for its schema is dataset specific
# it contains all the columns (column name has to be lower_cased and )


# # a fake cluster for initialization
# class Record(db.Model):
#     __tablename__ = 'record'
#     __table_args__ = {'extend_existing': True}
#
#     rid = db.Column(db.String, primary_key=True)

def construct_record_class(cols):
    attr_dict = {
        '__tablename__': f'record'
    }

    # columns
    for col in cols:
        if col == 'id':
            attr_dict['id'] = db.Column(db.String, primary_key=True)
        else:
            attr_dict[col] = db.Column(db.String)

    # create tsvector and GIN for full-text search
    all_cols = cols[:]
    all_cols.remove('id')
    all_cols = "|| ' ' ||".join(all_cols)
    attr_dict['__ts_vec__'] = db.Column(
        TSVector(),
        db.Computed(f"to_tsvector('english', {all_cols})",
        persisted=True)
    )
    attr_dict['__table_args__'] = (
        db.Index('__ts_idx__', '__ts_vec__', postgresql_using='gin'),
    )

    # create class
    record_class = type('Record', (db.Model,), attr_dict)

    # overwrite repr
    def repr(self):
        fmt_str = Meta.get('record_repr_format')
        if not fmt_str:  # if not format specified, use id instead
            return self.id
        return fmt_str.format(**{col: getattr(self, col) for col in cols})
    record_class.__repr__ = repr

    # bind relationships
    # record_class.relations = db.relationship('RecordClusterRelation', lazy=True)
    # record_class.clusters = db.relationship('Cluster', secondary=RecordClusterRelation.__table__, lazy=True,
    #                                         backref=db.backref('records', lazy=True))

    return record_class


def recover_record_class(raw_record_class_params):
    import json
    record_class_params = json.loads(raw_record_class_params)
    record_class = construct_record_class(**record_class_params)
    return record_class


CLUSTER_ANNOTATION_NULL = None
CLUSTER_ANNOTATION_ANNOTATED = 1
CLUSTER_ANNOTATION_IGNORED = 2


# class Cluster(db.Model):
#     __tablename__ = 'cluster'
#
#     id = db.Column(db.String, primary_key=True)
#     annotation = db.Column(db.Integer)  # NULL: not annotated, 1: annotated, 2: ignored
#     annotated_at = db.Column(db.DateTime)
#     annotated_by = db.Column(db.ForeignKey('user.id'))
#     relations = db.relationship('RecordClusterRelation', lazy=True)
#
#
# # def get_cluster_name(cluster_instance, record_class):
# #     return record_class.query.filter_by(id=cluster_instance.relations[0].rid).first()
#
#
# class RecordClusterRelation(db.Model):
#     __tablename__ = 'record_cluster_relation'
#
#     rid = db.Column(db.String, db.ForeignKey('record.id'))
#     cid = db.Column(db.String, db.ForeignKey('cluster.id'))
#     new_cid = db.Column(db.String)
#
#     __table_args__ = (
#         db.PrimaryKeyConstraint('rid', 'cid'),
#     )


# def bind_relation(record_class, cluster_class):
#     # dynamic binding for Record and Cluster
#     # record_class.cluster = db.relationship('Cluster', secondary=RecordClusterRelation.__table__, lazy=True)
#     cluster_class.records = db.relationship('Record', secondary=RecordClusterRelation.__table__, lazy=True,
#                                             backref=db.backref('clusters', lazy=True))


def construct_cluster_class(task_id):
    attr_dict = {
        '__tablename__': f'cluster_{task_id}',
        'id': db.Column(db.String, primary_key=True),
        'annotation': db.Column(db.Integer),  # NULL: not annotated, 1: annotated, 2: ignored
        'annotated_at': db.Column(db.DateTime),
        'annotated_by': db.Column(db.ForeignKey('user.id'))
    }
    cluster_class = type('Cluster', (db.Model,), attr_dict)
    # cluster_class.relations = db.relationship('RecordClusterRelation', lazy=True)

    return cluster_class


def construct_cluster_record_relation_class(task_id):
    attr_dict = {
        '__tablename__': f'record_cluster_relation_{task_id}',
        '__table_args__': (db.PrimaryKeyConstraint('rid', 'cid'),),
        'rid': db.Column(db.String, db.ForeignKey('record.id')),
        'cid': db.Column(db.String, db.ForeignKey(f'cluster_{task_id}.id')),
        'new_cid': db.Column(db.String)
    }
    relation_class = type('RecordClusterRelation', (db.Model,), attr_dict)

    return relation_class


def recover_cluster_class(task_id):
    return construct_cluster_class(task_id)


def recover_cluster_record_relation_class(task_id):
    return construct_cluster_record_relation_class(task_id)


def bind_relationships(record_class, cluster_class, cluster_record_relation_class):
    # Record
    record_class.relations = db.relationship('RecordClusterRelation', lazy=True)
    record_class.clusters = db.relationship('Cluster', secondary=cluster_record_relation_class.__table__, lazy=True,
                                            backref=db.backref('records', lazy=True))

    # Cluster
    cluster_class.relations = db.relationship('RecordClusterRelation', lazy=True)


class Meta(db.Model):
    __tablename__ = 'meta'

    key = db.Column(db.String, primary_key=True)
    value = db.Column(db.String)

    # key: value
    #
    # mode: split | merge | idle
    # record_class_params: json.dumps({'cols': []})
    # record_repr_format: 'addr: {address}'
    # task_id: str(6)

    @classmethod
    def get(cls, key):
        try:
            return cls.query.get(key).value
        except:
            return None

    @classmethod
    def set(cls, key, value):
        meta = cls.query.get(key)
        meta.value = value
        db.session.commit()
