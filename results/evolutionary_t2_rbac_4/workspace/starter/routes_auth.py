"""
T2 RBAC System -- Auth Routes (Sample 2: Early-Return Variant)

Login endpoint with JWT generation.

Design decisions:
- Early return pattern: each validation step returns immediately on failure,
  avoiding deeply nested if/else blocks. This keeps the happy path at the
  bottom with minimal indentation.
- JWT generation extracted into a standalone helper (_build_jwt) so it can
  be tested or reused independently without touching the request context.
- Uses `jsonify` for all responses to guarantee Content-Type: application/json.
- Password comparison is delegated entirely to middleware.hash_password().
"""

from datetime import datetime, timedelta

import jwt as pyjwt
from flask import Blueprint, request, jsonify, current_app

from models import User
from middleware import hash_password

auth_bp = Blueprint('auth_bp', __name__)


def _build_jwt(user_id: int, tenant_id: int) -> str:
    """Generate a signed JWT containing user_id, tenant_id, and exp.

    The secret and expiry window are read from the Flask app config so that
    tests can override them without patching environment variables.
    """
    secret = current_app.config['JWT_SECRET']
    expiry_hours = current_app.config['JWT_EXPIRY_HOURS']
    now = datetime.utcnow()
    payload = {
        'user_id': user_id,
        'tenant_id': tenant_id,
        'exp': now + timedelta(hours=expiry_hours),
    }
    return pyjwt.encode(payload, secret, algorithm='HS256')


@auth_bp.route('/login', methods=['POST'])
def login():
    """Authenticate a user and return a JWT token.

    Request JSON:
        {"username": str, "password": str}

    Success (200):
        {"status": "ok", "data": {"token": "<jwt-string>"}}

    Errors:
        400 -- username or password field missing
        401 -- user does not exist or password mismatch
    """
    body = request.get_json(silent=True)

    # --- Validate request body ---
    if body is None or not isinstance(body, dict):
        return jsonify({'status': 'error', 'message': 'Invalid request body'}), 400

    if 'username' not in body or not body['username']:
        return jsonify({'status': 'error', 'message': 'Missing username'}), 400

    if 'password' not in body or not body['password']:
        return jsonify({'status': 'error', 'message': 'Missing password'}), 400

    username = body['username']
    password = body['password']

    # --- Lookup user ---
    user = User.query.filter_by(username=username).first()

    if user is None:
        return jsonify({'status': 'error', 'message': 'Invalid credentials'}), 401

    # --- Verify password ---
    if user.password_hash != hash_password(password):
        return jsonify({'status': 'error', 'message': 'Invalid credentials'}), 401

    # --- Success: issue token ---
    token = _build_jwt(user.id, user.tenant_id)

    return jsonify({'status': 'ok', 'data': {'token': token}}), 200
