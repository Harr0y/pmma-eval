"""
T2 RBAC System — Auth Routes (Sample 1: Gen 1, Developer)

Login endpoint implementation.
Uses Blueprint named 'auth_bp'.

Design decisions:
- JWT generation encapsulated in a helper function (_generate_jwt) for clarity.
- Direct, no-frills approach: validate input, look up user, compare hash, issue token.
- Errors use the standard {"status": "error", "message": ...} envelope.
"""

import jwt as pyjwt
from datetime import datetime, timezone, timedelta
from flask import Blueprint, request, jsonify, current_app

from models import User
from middleware import hash_password

auth_bp = Blueprint('auth_bp', __name__)


def _generate_jwt(user_id, tenant_id):
    """Generate a JWT containing user_id, tenant_id, and exp claim."""
    secret = current_app.config['JWT_SECRET']
    expiry_hours = current_app.config['JWT_EXPIRY_HOURS']
    payload = {
        'user_id': user_id,
        'tenant_id': tenant_id,
        'exp': datetime.now(timezone.utc) + timedelta(hours=expiry_hours),
    }
    return pyjwt.encode(payload, secret, algorithm='HS256')


@auth_bp.route('/login', methods=['POST'])
def login():
    data = request.get_json(silent=True)

    # Validate required fields
    if not data or not isinstance(data, dict):
        return jsonify({'status': 'error', 'message': 'Request body must be JSON'}), 400

    username = data.get('username')
    password = data.get('password')

    if not username or not password:
        return jsonify({'status': 'error', 'message': 'username and password are required'}), 400

    # Look up user
    user = User.query.filter_by(username=username).first()
    if user is None:
        return jsonify({'status': 'error', 'message': 'Invalid credentials'}), 401

    # Verify password
    if user.password_hash != hash_password(password):
        return jsonify({'status': 'error', 'message': 'Invalid credentials'}), 401

    # Issue token
    token = _generate_jwt(user.id, user.tenant_id)
    return jsonify({'status': 'ok', 'data': {'token': token}})
