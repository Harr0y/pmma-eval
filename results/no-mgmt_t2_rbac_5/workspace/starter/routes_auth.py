"""
T2 RBAC System — Auth Routes

Login and token management.
Register as a Flask Blueprint named 'auth_bp'.
"""

from flask import Blueprint, request, jsonify
import datetime
import jwt as pyjwt
from models import User
from middleware import hash_password
from app import db

auth_bp = Blueprint('auth_bp', __name__)


@auth_bp.route('/login', methods=['POST'])
def login():
    data = request.get_json(silent=True) or {}
    username = data.get('username')
    password = data.get('password')

    if not username or not password:
        return jsonify({'status': 'error', 'message': 'Username and password required'}), 400

    user = User.query.filter_by(username=username).first()
    if user is None or user.password_hash != hash_password(password):
        return jsonify({'status': 'error', 'message': 'Invalid credentials'}), 401

    from flask import current_app
    secret = current_app.config.get('JWT_SECRET', 'dev-secret-key')
    expiry_hours = current_app.config.get('JWT_EXPIRY_HOURS', 24)
    exp = datetime.datetime.utcnow() + datetime.timedelta(hours=expiry_hours)

    token = pyjwt.encode(
        {'user_id': user.id, 'tenant_id': user.tenant_id, 'exp': exp},
        secret, algorithm='HS256'
    )

    return jsonify({'status': 'ok', 'data': {'token': token}})
