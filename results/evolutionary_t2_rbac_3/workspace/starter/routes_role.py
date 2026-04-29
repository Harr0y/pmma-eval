"""
T2 RBAC System — Role Management Routes (Sample 2)

Variant strategy:
- require_auth decorator for authentication, then manual role.manage check
- Helper functions for response building and role serialization
- BFS-based inheritance cycle detection (not recursive)
- Early-return error pattern

Register as Flask Blueprint named 'role_bp'.
"""

from collections import deque
from flask import Blueprint, request, jsonify, g
from middleware import require_auth
from models import Role, Permission, User, role_permissions, user_roles
from app import db

role_bp = Blueprint('role_bp', __name__)


def _ok(data, status=200):
    return jsonify({'status': 'ok', 'data': data}), status


def _err(message, status):
    return jsonify({'status': 'error', 'message': message}), status


def _serialize_role(role):
    """Convert a Role model instance to a dict including its direct permissions."""
    return {
        'id': role.id,
        'name': role.name,
        'parent_role_id': role.parent_role_id,
        'permissions': [p.code for p in role.permissions],
    }


def _check_perm(code):
    """Check if the current user has a specific permission."""
    return code in g.get('current_permissions', set())


def _has_inheritance_cycle(role_id, target_parent_id):
    """Detect if setting role_id's parent to target_parent_id would create a cycle.

    Uses BFS/iteration: walk the parent chain upward from target_parent_id.
    If we encounter role_id along the way, setting this parent would create a cycle.

    Returns True if a cycle would be formed.
    """
    visited = set()
    queue = deque([target_parent_id])

    while queue:
        current_id = queue.popleft()
        if current_id == role_id:
            return True
        if current_id in visited:
            continue
        visited.add(current_id)

        current_role = Role.query.get(current_id)
        if current_role and current_role.parent_role_id is not None:
            queue.append(current_role.parent_role_id)

    return False


def _resolve_permissions(perm_codes):
    """Look up Permission records by code strings. Returns (list, error_response).
    If any code is not found, returns ([], error).
    """
    if not perm_codes:
        return [], None

    perms = Permission.query.filter(Permission.code.in_(perm_codes)).all()
    found_codes = {p.code for p in perms}
    missing = set(perm_codes) - found_codes
    if missing:
        return [], _err(f'Unknown permissions: {", ".join(sorted(missing))}', 400)
    return perms, None


@role_bp.route('/roles', methods=['POST'])
@require_auth
def create_role():
    if not _check_perm('role.manage'):
        return _err('Permission denied', 403)

    body = request.get_json(silent=True)
    if not body:
        return _err('Missing request body', 400)

    name = body.get('name')
    if not name:
        return _err('Role name is required', 400)

    tenant_id = g.current_user.tenant_id

    # Check duplicate name within tenant
    existing = Role.query.filter_by(tenant_id=tenant_id, name=name).first()
    if existing:
        return _err(f'Role "{name}" already exists in this tenant', 409)

    parent_role_id = body.get('parent_role_id')
    if parent_role_id is not None:
        parent = Role.query.get(parent_role_id)
        if parent is None or parent.tenant_id != tenant_id:
            return _err('Parent role not found or belongs to a different tenant', 400)

    perms, err = _resolve_permissions(body.get('permissions', []))
    if err:
        return err

    role = Role(tenant_id=tenant_id, name=name, parent_role_id=parent_role_id)
    role.permissions = perms
    db.session.add(role)
    db.session.commit()

    return _ok(_serialize_role(role), 201)


@role_bp.route('/roles', methods=['GET'])
@require_auth
def list_roles():
    if not _check_perm('role.manage'):
        return _err('Permission denied', 403)

    tenant_id = g.current_user.tenant_id
    roles = Role.query.filter_by(tenant_id=tenant_id).all()
    return _ok([_serialize_role(r) for r in roles])


@role_bp.route('/roles/<int:role_id>/permissions', methods=['PUT'])
@require_auth
def update_role_permissions(role_id):
    if not _check_perm('role.manage'):
        return _err('Permission denied', 403)

    role = Role.query.get(role_id)
    if role is None:
        return _err('Role not found', 404)

    body = request.get_json(silent=True)
    if not body:
        return _err('Missing request body', 400)

    parent_role_id = body.get('parent_role_id')
    if parent_role_id is not None:
        # Validate parent belongs to same tenant
        parent = Role.query.get(parent_role_id)
        if parent is None or parent.tenant_id != role.tenant_id:
            return _err('Parent role not found or belongs to a different tenant', 400)

        # Cycle detection: would setting parent_role_id on role_id create a cycle?
        if _has_inheritance_cycle(role_id, parent_role_id):
            return _err('Inheritance cycle detected', 400)

        role.parent_role_id = parent_role_id
    else:
        # Explicitly clear parent if parent_role_id is None in body
        if 'parent_role_id' in body:
            role.parent_role_id = None

    # Replace permissions
    perm_codes = body.get('permissions')
    if perm_codes is not None:
        perms, err = _resolve_permissions(perm_codes)
        if err:
            return err
        role.permissions = perms

    db.session.commit()
    return _ok(_serialize_role(role))


@role_bp.route('/users/<int:user_id>/roles', methods=['POST'])
@require_auth
def assign_role(user_id):
    if not _check_perm('role.manage'):
        return _err('Permission denied', 403)

    body = request.get_json(silent=True)
    if not body:
        return _err('Missing request body', 400)

    role_id = body.get('role_id')
    if role_id is None:
        return _err('role_id is required', 400)

    user = User.query.get(user_id)
    if user is None:
        return _err('User not found', 404)

    role = Role.query.get(role_id)
    if role is None:
        return _err('Role not found', 404)

    # Cross-tenant check
    if user.tenant_id != g.current_user.tenant_id:
        return _err('Cannot assign roles to users in other tenants', 403)

    if role.tenant_id != g.current_user.tenant_id:
        return _err('Cannot assign roles from other tenants', 403)

    # Check if already assigned (avoid duplicate insert)
    existing = db.session.query(user_roles).filter_by(
        user_id=user_id, role_id=role_id
    ).first()
    if existing:
        return _ok({'user_id': user_id, 'role_id': role_id})

    db.session.execute(user_roles.insert().values(user_id=user_id, role_id=role_id))
    db.session.commit()
    return _ok({'user_id': user_id, 'role_id': role_id})


@role_bp.route('/users/<int:user_id>/roles/<int:role_id>', methods=['DELETE'])
@require_auth
def remove_role(user_id, role_id):
    if not _check_perm('role.manage'):
        return _err('Permission denied', 403)

    user = User.query.get(user_id)
    if user is None:
        return _err('User not found', 404)

    # Idempotent: delete if exists, no error if not
    db.session.execute(
        user_roles.delete().where(
            user_roles.c.user_id == user_id,
            user_roles.c.role_id == role_id
        )
    )
    db.session.commit()
    return _ok({'user_id': user_id, 'role_id': role_id})
