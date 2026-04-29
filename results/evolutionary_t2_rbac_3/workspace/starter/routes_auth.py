"""
T2 RBAC System — Auth Routes (Sample 2)

Variant strategy:
- No external decorators; JWT encoding/decoding done inline
- Helper function for response building
- Early-return error pattern

Register as Flask Blueprint named 'auth_bp'.
"""

import jwt as pyjwt
import datetime
from flask import Blueprint, request, jsonify, current_app
from models import User
from middleware import hash_password

auth_bp = Blueprint('auth_bp', __name__)


def _ok(data):
    """Build a success response."""
    return jsonify({'status': 'ok', 'data': data})


def _err(message, status):
    """Build an error response."""
    return jsonify({'status': 'error', 'message': message}), status


@auth_bp.route('/login', methods=['POST'])
def login():
    body = request.get_json(silent=True)
    if not body:
        return _err('Missing request body', 400)

    username = body.get('username')
    password = body.get('password')

    if not username or not password:
        return _err('Username and password are required', 400)

    user = User.query.filter_by(username=username).first()
    if user is None:
        return _err('Invalid credentials', 401)

    if user.password_hash != hash_password(password):
        return _err('Invalid credentials', 401)

    secret = current_app.config.get('JWT_SECRET', 'dev-secret-key')
    expiry_hours = current_app.config.get('JWT_EXPIRY_HOURS', 24)
    exp = datetime.datetime.utcnow() + datetime.timedelta(hours=expiry_hours)

    token = pyjwt.encode(
        {'user_id': user.id, 'tenant_id': user.tenant_id, 'exp': exp},
        secret,
        algorithm='HS256'
    )

    return _ok({'token': token})
