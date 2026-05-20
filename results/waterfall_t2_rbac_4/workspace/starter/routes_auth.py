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

from flask import Blueprint, request, jsonify, current_app
import jwt as pyjwt
import datetime

from models import User
from middleware import hash_password

auth_bp = Blueprint('auth_bp', __name__)


@auth_bp.route('/login', methods=['POST'])
def login():
    """Authenticate user and return JWT token.

    Design spec (design.md 2.1):
    0. Parse JSON body with silent=True; None -> 400
    1. Validate username and password present; missing -> 400
    2. Query User by username; not found -> 401
    3. Hash password and compare with stored hash; mismatch -> 401
    4. Generate JWT with payload {user_id, tenant_id, exp}
    5. Return token
    """
    # Step 0: Parse request body
    data = request.get_json(silent=True)
    if data is None:
        return jsonify({'status': 'error', 'message': 'Invalid request'}), 400

    # Step 1: Validate required fields
    username = data.get('username')
    password = data.get('password')
    if not username or not password:
        return jsonify({'status': 'error', 'message': 'Username and password are required'}), 400

    # Step 2: Look up user by username
    user = User.query.filter_by(username=username).first()
    if user is None:
        return jsonify({'status': 'error', 'message': 'Invalid credentials'}), 401

    # Step 3: Verify password
    if hash_password(password) != user.password_hash:
        return jsonify({'status': 'error', 'message': 'Invalid credentials'}), 401

    # Step 4: Generate JWT
    secret = current_app.config['JWT_SECRET']
    expiry_hours = current_app.config.get('JWT_EXPIRY_HOURS', 24)
    now = datetime.datetime.utcnow()
    payload = {
        'user_id': user.id,
        'tenant_id': user.tenant_id,
        'exp': now + datetime.timedelta(hours=expiry_hours),
    }
    token = pyjwt.encode(payload, secret, algorithm='HS256')

    # Step 5: Return token
    return jsonify({'status': 'ok', 'data': {'token': token}}), 200
