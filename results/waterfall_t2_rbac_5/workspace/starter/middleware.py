"""
T2 RBAC System — Middleware

JWT verification and permission checking with role inheritance.
"""

import jwt as pyjwt
from flask import request, jsonify, g, current_app
from functools import wraps
from models import User, Role, Permission, role_permissions, user_roles
from app import db


def hash_password(password):
    """Simple password hash (for demo purposes)."""
    import hashlib
    return hashlib.sha256(password.encode()).hexdigest()


def decode_token(token):
    """Decode and verify JWT token. Returns payload or None."""
    try:
        secret = current_app.config.get('JWT_SECRET', 'dev-secret-key')
        payload = pyjwt.decode(token, secret, algorithms=['HS256'])
        return payload
    except (pyjwt.ExpiredSignatureError, pyjwt.InvalidTokenError):
        return None


def get_current_user():
    """Extract current user from JWT in Authorization header.
    Returns (user_record, error_response) tuple.
    """
    auth_header = request.headers.get('Authorization', '')
    if not auth_header.startswith('Bearer '):
        return None, (jsonify({'status': 'error', 'message': 'Missing token'}), 401)

    token = auth_header[7:]
    payload = decode_token(token)
    if payload is None:
        return None, (jsonify({'status': 'error', 'message': 'Invalid or expired token'}), 401)

    user = User.query.get(payload.get('user_id'))
    if user is None:
        return None, (jsonify({'status': 'error', 'message': 'User not found'}), 401)

    return user, None


def get_user_permissions(user):
    """Get all permissions for a user, including inherited ones from role hierarchy."""
    permissions = set()
    for role in user.roles:
        permissions.update(_collect_role_permissions(role))
    return permissions


def _collect_role_permissions(role, visited=None):
    """Recursively collect permissions from a role and its parent chain."""
    if visited is None:
        visited = set()
    if role.id in visited:
        return set()
    visited.add(role.id)

    perms = set(p.code for p in role.permissions)
    if role.parent_role_id:
        parent = Role.query.get(role.parent_role_id)
        if parent:
            perms.update(_collect_role_permissions(parent, visited))
    return perms


def check_permission(permission_code):
    """Decorator to check if current user has a specific permission."""
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            user, error = get_current_user()
            if error:
                return error

            perms = get_user_permissions(user)
            if permission_code not in perms:
                return jsonify({'status': 'error', 'message': 'Permission denied'}), 403

            g.current_user = user
            g.current_permissions = perms
            return f(*args, **kwargs)
        return decorated_function
    return decorator


def require_auth(f):
    """Decorator to require authentication without specific permission."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        user, error = get_current_user()
        if error:
            return error
        g.current_user = user
        g.current_permissions = get_user_permissions(user)
        return f(*args, **kwargs)
    return decorated_function
