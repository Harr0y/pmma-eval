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

import jwt as pyjwt
from datetime import datetime, timedelta
from flask import Blueprint, request, jsonify, current_app
from middleware import hash_password
from models import User

auth_bp = Blueprint('auth_bp', __name__)


@auth_bp.route('/login', methods=['POST'])
def login():
    data = request.get_json(silent=True)

    # 1. Validate request body: username and password must be present
    if not data or not data.get('username') or not data.get('password'):
        return jsonify({'status': 'error', 'message': 'Username and password are required'}), 400

    username = data['username']
    password = data['password']

    # 2. Query User by username
    user = User.query.filter_by(username=username).first()

    # 3. Verify password: hash_password(password) == user.password_hash
    # 4. User not found or password mismatch → 401
    if not user or hash_password(password) != user.password_hash:
        return jsonify({'status': 'error', 'message': 'Invalid credentials'}), 401

    # 5. Generate JWT token
    jwt_secret = current_app.config['JWT_SECRET']
    jwt_expiry_hours = current_app.config['JWT_EXPIRY_HOURS']
    payload = {
        'user_id': user.id,
        'tenant_id': user.tenant_id,
        'exp': datetime.utcnow() + timedelta(hours=jwt_expiry_hours),
    }
    token = pyjwt.encode(payload, jwt_secret, algorithm='HS256')

    # 6. Return success response
    return jsonify({'status': 'ok', 'data': {'token': token}}), 200
