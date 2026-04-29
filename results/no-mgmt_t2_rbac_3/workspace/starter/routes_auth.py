"""
T2 RBAC System — Auth Routes

Login and token management.
Register as a Flask Blueprint named 'auth_bp'.
"""

import jwt as pyjwt
from datetime import datetime, timedelta
from flask import Blueprint, request, jsonify, current_app
from models import User
from middleware import hash_password

auth_bp = Blueprint('auth_bp', __name__)


@auth_bp.route('/login', methods=['POST'])
def login():
    data = request.get_json(silent=True)
    if not data or not data.get('username') or not data.get('password'):
        return jsonify({'status': 'error', 'message': 'Username and password required'}), 400

    username = data['username']
    password = data['password']

    user = User.query.filter_by(username=username).first()
    if user is None or user.password_hash != hash_password(password):
        return jsonify({'status': 'error', 'message': 'Invalid credentials'}), 401

    secret = current_app.config.get('JWT_SECRET', 'dev-secret-key')
    expiry_hours = current_app.config.get('JWT_EXPIRY_HOURS', 24)
    payload = {
        'user_id': user.id,
        'tenant_id': user.tenant_id,
        'exp': datetime.utcnow() + timedelta(hours=expiry_hours),
    }
    token = pyjwt.encode(payload, secret, algorithm='HS256')

    return jsonify({'status': 'ok', 'data': {'token': token}}), 200
