"""
T2 RBAC System — Auth Routes (Sample 1)

Login endpoint that issues JWT tokens.
Variant strategy: separate token builder as a composable helper,
validate input via explicit key-presence + non-empty-string check.
"""

import datetime
import jwt as pyjwt
from flask import Blueprint, request, jsonify, current_app, g
from models import User
from middleware import hash_password

auth_bp = Blueprint('auth_bp', __name__)


def _build_jwt(user_id, tenant_id, secret, expiry_hours):
    """Compose a JWT with user identity and expiry claim."""
    now = datetime.datetime.utcnow()
    payload = {
        'user_id': user_id,
        'tenant_id': tenant_id,
        'exp': now + datetime.timedelta(hours=expiry_hours),
        'iat': now,
    }
    return pyjwt.encode(payload, secret, algorithm='HS256')


@auth_bp.route('/login', methods=['POST'])
def login():
    body = request.get_json(silent=True)
    if not isinstance(body, dict):
        return jsonify({'status': 'error', 'message': 'Request body must be JSON'}), 400

    username = body.get('username')
    password = body.get('password')

    # Reject missing or empty-string credentials
    if not username or not isinstance(username, str) or not password or not isinstance(password, str):
        return jsonify({'status': 'error', 'message': 'username and password are required'}), 400

    user = User.query.filter_by(username=username).first()
    if user is None or user.password_hash != hash_password(password):
        return jsonify({'status': 'error', 'message': 'Invalid credentials'}), 401

    secret = current_app.config.get('JWT_SECRET', 'dev-secret-key')
    expiry = current_app.config.get('JWT_EXPIRY_HOURS', 24)
    token = _build_jwt(user.id, user.tenant_id, secret, expiry)

    g.current_user = user
    return jsonify({'status': 'ok', 'data': {'token': token}}), 200
