"""
T2 RBAC System — Auth Routes (Sample 1 Variant)

Login endpoint with input validation extracted into helper functions.
Uses request.get_json(silent=True) for robust body parsing and
datetime.timedelta for expiry calculation.

Register as a Flask Blueprint named 'auth_bp'.
"""

import datetime

import jwt as pyjwt
from flask import Blueprint, request, jsonify, current_app

from models import User
from middleware import hash_password

auth_bp = Blueprint('auth_bp', __name__)


def _parse_login_input(body):
    """Extract and validate login fields from the request body.

    Returns a (username, password, error_response) tuple.
    On success, error_response is None. On validation failure, returns
    the appropriate (username, password, (response, status_code)) pair.
    """
    if not isinstance(body, dict):
        return None, None, (jsonify({'status': 'error', 'message': 'Request body must be a JSON object'}), 400)

    username = body.get('username')
    password = body.get('password')

    if not username or not isinstance(username, str):
        return None, None, (jsonify({'status': 'error', 'message': 'Missing or invalid username'}), 400)
    if not password or not isinstance(password, str):
        return None, None, (jsonify({'status': 'error', 'message': 'Missing or invalid password'}), 400)

    return username, password, None


def _authenticate_user(username, password):
    """Look up the user by username and verify the password.

    Returns (user, error_response) tuple. On success, error_response is None.
    On failure, returns (None, (response, status_code)).
    """
    user = User.query.filter_by(username=username).first()
    if user is None:
        return None, (jsonify({'status': 'error', 'message': 'Invalid credentials'}), 401)

    expected_hash = hash_password(password)
    if user.password_hash != expected_hash:
        return None, (jsonify({'status': 'error', 'message': 'Invalid credentials'}), 401)

    return user, None


def _issue_token(user):
    """Generate a JWT token for the given user.

    Token payload includes user_id, tenant_id, and exp (calculated via timedelta).
    """
    secret = current_app.config['JWT_SECRET']
    expiry_hours = current_app.config.get('JWT_EXPIRY_HOURS', 24)

    now = datetime.datetime.utcnow()
    payload = {
        'user_id': user.id,
        'tenant_id': user.tenant_id,
        'exp': now + datetime.timedelta(hours=expiry_hours),
    }

    token = pyjwt.encode(payload, secret, algorithm='HS256')
    return token


@auth_bp.route('/login', methods=['POST'])
def login():
    """POST /login — Authenticate user and return a JWT token.

    Request body (JSON):
        {"username": str, "password": str}

    Success response (200):
        {"status": "ok", "data": {"token": str}}

    Error responses:
        400 — Missing or invalid username/password
        401 — User not found or password mismatch
    """
    body = request.get_json(silent=True)

    # Step 1: Parse and validate input
    username, password, validation_error = _parse_login_input(body)
    if validation_error:
        return validation_error

    # Step 2: Authenticate against the database
    user, auth_error = _authenticate_user(username, password)
    if auth_error:
        return auth_error

    # Step 3: Issue JWT
    token = _issue_token(user)

    return jsonify({
        'status': 'ok',
        'data': {'token': token},
    }), 200
