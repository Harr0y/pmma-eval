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
    """Authenticate a user and return a JWT token.

    Validates that username and password are present in the JSON body,
    checks credentials against the database, and returns a signed JWT
    containing user_id, tenant_id, and expiration.
    """
    # Handle non-JSON requests: force=True skips Content-Type check so
    # non-JSON bodies reach our validation instead of getting a 415 from Flask.
    data = request.get_json(force=True, silent=True)
    if data is None:
        return jsonify({'status': 'error', 'message': 'Request must be JSON'}), 400

    username = data.get('username')
    password = data.get('password')

    # Validate that both username and password are provided and non-empty
    if not username or not password:
        return jsonify({'status': 'error', 'message': 'Username and password are required'}), 400

    # Look up the user by username
    user = User.query.filter_by(username=username).first()
    if user is None:
        return jsonify({'status': 'error', 'message': 'Invalid credentials'}), 401

    # Verify password by hashing the input and comparing with stored hash
    if hash_password(password) != user.password_hash:
        return jsonify({'status': 'error', 'message': 'Invalid credentials'}), 401

    # Generate JWT with user_id, tenant_id, and expiration
    payload = {
        'user_id': user.id,
        'tenant_id': user.tenant_id,
        'exp': datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(hours=current_app.config['JWT_EXPIRY_HOURS']),
    }
    token = pyjwt.encode(payload, current_app.config['JWT_SECRET'], algorithm='HS256')

    return jsonify({'status': 'ok', 'data': {'token': token}}), 200
