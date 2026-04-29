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
from datetime import datetime, timedelta
from models import User
from middleware import hash_password

auth_bp = Blueprint('auth_bp', __name__)


@auth_bp.route('/login', methods=['POST'])
def login():
    # Step 1: Parse request JSON
    if not request.is_json:
        return jsonify({'status': 'error', 'message': 'Request must be JSON'}), 400

    data = request.get_json(silent=True)
    if data is None:
        return jsonify({'status': 'error', 'message': 'Invalid JSON'}), 400

    # Step 2: Validate required fields (missing or empty string -> 400)
    username = data.get('username')
    password = data.get('password')

    if not username or not isinstance(username, str) or not username.strip():
        return jsonify({'status': 'error', 'message': 'username is required'}), 400
    if not password or not isinstance(password, str) or not password.strip():
        return jsonify({'status': 'error', 'message': 'password is required'}), 400

    # Step 3: Query user by username
    user = User.query.filter_by(username=username.strip()).first()

    # Step 4 & 5: User not found or password mismatch -> 401 (unified, prevent enumeration)
    if user is None or hash_password(password) != user.password_hash:
        return jsonify({'status': 'error', 'message': 'Invalid credentials'}), 401

    # Step 6: Generate JWT token
    payload = {
        'user_id': user.id,
        'tenant_id': user.tenant_id,
        'exp': datetime.utcnow() + timedelta(hours=current_app.config['JWT_EXPIRY_HOURS'])
    }
    token = pyjwt.encode(payload, current_app.config['JWT_SECRET'], algorithm='HS256')

    # Step 7: Return success response
    return jsonify({'status': 'ok', 'data': {'token': token}}), 200
