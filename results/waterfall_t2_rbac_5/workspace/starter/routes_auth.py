"""
T2 RBAC System — Auth Routes

Login and token management.
Register as a Flask Blueprint named 'auth_bp'.

Requirements:
- POST /login -> User login, returns JWT token
  Request: {"username": str, "password": str}
  Response: {"status": "ok", "data": {"token": str}}
  - JWT payload contains: user_id, tenant_id, exp
  - Password is verified using middleware.hash_password()
Errors: 400 if username or password missing, 401 if invalid credentials

IMPORTANT: The JWT token is used by all other routes via middleware.get_current_user().
Token must contain user_id and tenant_id for proper RBAC enforcement.
"""

from datetime import datetime, timedelta

import jwt as pyjwt
from flask import Blueprint, request, jsonify, current_app

from models import User
from middleware import hash_password

auth_bp = Blueprint('auth_bp', __name__)


@auth_bp.route('/login', methods=['POST'])
def login():
    """Authenticate user and return JWT token.

    Request body: {"username": str, "password": str}
    Success (200): {"status": "ok", "data": {"token": str}}
    Error (400): missing username or password
    Error (401): user not found or password mismatch
    """
    data = request.get_json(silent=True)
    if not data or not isinstance(data, dict):
        return jsonify({"status": "error", "message": "Missing username or password"}), 400

    username = data.get('username')
    password = data.get('password')

    if not username or not password:
        return jsonify({"status": "error", "message": "Missing username or password"}), 400

    user = User.query.filter_by(username=username).first()
    if user is None or user.password_hash != hash_password(password):
        return jsonify({"status": "error", "message": "Invalid username or password"}), 401

    secret = current_app.config.get('JWT_SECRET', 'dev-secret-key')
    expiry_hours = current_app.config.get('JWT_EXPIRY_HOURS', 24)
    payload = {
        'user_id': user.id,
        'tenant_id': user.tenant_id,
        'exp': datetime.utcnow() + timedelta(hours=expiry_hours),
    }
    token = pyjwt.encode(payload, secret, algorithm='HS256')

    return jsonify({"status": "ok", "data": {"token": token}}), 200
