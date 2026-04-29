"""
T2 RBAC System — Role Management Routes

Role CRUD, user-role assignment, permission management.
Register as a Flask Blueprint named 'role_bp'.
All operations require role.manage permission.

Requirements:
- POST /roles -> Create role
  Requires: role.manage
  Request: {"name": str, "parent_role_id": int|null, "permissions": [str, ...]}
  Response: {"status": "ok", "data": {"id": int, "name": str, "parent_role_id": int|null,
            "permissions": [str, ...]}}
  - Must check for duplicate role names within same tenant
  - parent_role_id must belong to same tenant
  Errors: 400 if name missing or parent invalid, 409 if duplicate name

- GET /roles -> List roles for current tenant
  Requires: role.manage
  Response: {"status": "ok", "data": [...]}

- PUT /roles/<id>/permissions -> Update role permissions and/or parent
  Requires: role.manage
  Request: {"permissions": [str, ...], "parent_role_id": int|null}
  - Must detect inheritance cycles when setting parent_role_id
  Errors: 404 if role not found, 400 if cycle detected or parent invalid

- POST /users/<id>/roles -> Assign role to user
  Requires: role.manage
  Request: {"role_id": int}
  - Both user and role must belong to same tenant
  Errors: 404 if user or role not found

- DELETE /users/<id>/roles/<role_id> -> Remove role from user
  Requires: role.manage
  - Idempotent — no error if role not assigned
  Errors: 404 if user not found

IMPORTANT: Role inheritance is handled by middleware._collect_role_permissions().
Roles are tenant-scoped. This module works with middleware.py and routes_document.py.
"""

from flask import Blueprint, request, jsonify, g
from middleware import check_permission
from models import Role, Permission, User, user_roles, role_permissions
from app import db

role_bp = Blueprint('role_bp', __name__)


def _role_dict(role):
    """Serialize a Role model to dict, including its permission codes."""
    return {
        'id': role.id,
        'name': role.name,
        'parent_role_id': role.parent_role_id,
        'permissions': [p.code for p in role.permissions],
    }


def _would_create_cycle(role_id, new_parent_id):
    """Check if setting role's parent to new_parent_id would create a cycle.

    Walks the ancestor chain from new_parent_id upward.
    If we encounter role_id (including the trivial case where new_parent_id == role_id),
    it's a cycle.
    """
    visited = set()
    current_id = new_parent_id
    while current_id is not None:
        if current_id == role_id:
            return True
        if current_id in visited:
            # Already-visited node means an existing cycle in DB; reject to be safe.
            return True
        visited.add(current_id)
        current_role = Role.query.get(current_id)
        if current_role is None:
            break
        current_id = current_role.parent_role_id
    return False


@role_bp.route('/roles', methods=['POST'])
@check_permission('role.manage')
def create_role():
    """Create a new role in the current user's tenant."""
    user = g.current_user
    data = request.get_json(silent=True)
    if not data:
        return jsonify({'status': 'error', 'message': 'Missing request body'}), 400

    name = data.get('name')
    if not name:
        return jsonify({'status': 'error', 'message': 'Missing role name'}), 400

    # Check duplicate name within same tenant
    existing = Role.query.filter_by(tenant_id=user.tenant_id, name=name).first()
    if existing is not None:
        return jsonify({'status': 'error', 'message': 'Role name already exists in this tenant'}), 409

    parent_role_id = data.get('parent_role_id')
    if parent_role_id is not None:
        parent = Role.query.get(parent_role_id)
        if parent is None or parent.tenant_id != user.tenant_id:
            return jsonify({'status': 'error', 'message': 'Parent role not found or belongs to different tenant'}), 400

    permission_codes = data.get('permissions', [])
    perms = []
    for code in permission_codes:
        perm = Permission.query.filter_by(code=code).first()
        if perm is not None:
            perms.append(perm)

    role = Role(tenant_id=user.tenant_id, name=name, parent_role_id=parent_role_id)
    role.permissions = perms
    db.session.add(role)
    db.session.commit()

    return jsonify({'status': 'ok', 'data': _role_dict(role)}), 201


@role_bp.route('/roles', methods=['GET'])
@check_permission('role.manage')
def list_roles():
    """List all roles for the current user's tenant."""
    user = g.current_user
    roles = Role.query.filter_by(tenant_id=user.tenant_id).all()
    return jsonify({'status': 'ok', 'data': [_role_dict(r) for r in roles]}), 200


@role_bp.route('/roles/<int:role_id>/permissions', methods=['PUT'])
@check_permission('role.manage')
def update_role_permissions(role_id):
    """Update a role's permission set and/or parent role."""
    user = g.current_user
    role = Role.query.get(role_id)
    if role is None or role.tenant_id != user.tenant_id:
        return jsonify({'status': 'error', 'message': 'Role not found'}), 404

    data = request.get_json(silent=True)
    if not data:
        return jsonify({'status': 'error', 'message': 'Missing request body'}), 400

    # Update parent_role_id if provided
    if 'parent_role_id' in data:
        new_parent_id = data['parent_role_id']
        if new_parent_id is not None:
            parent = Role.query.get(new_parent_id)
            if parent is None or parent.tenant_id != user.tenant_id:
                return jsonify({'status': 'error', 'message': 'Parent role not found or belongs to different tenant'}), 400
            # Cycle detection: new_parent's ancestor chain must not include this role
            if _would_create_cycle(role_id, new_parent_id):
                return jsonify({'status': 'error', 'message': 'Inheritance cycle detected'}), 400
        role.parent_role_id = new_parent_id

    # Replace permissions if provided
    if 'permissions' in data:
        permission_codes = data['permissions']
        perms = []
        for code in permission_codes:
            perm = Permission.query.filter_by(code=code).first()
            if perm is not None:
                perms.append(perm)
        role.permissions = perms

    db.session.commit()
    return jsonify({'status': 'ok', 'data': _role_dict(role)}), 200


@role_bp.route('/users/<int:user_id>/roles', methods=['POST'])
@check_permission('role.manage')
def assign_role(user_id):
    """Assign a role to a user. Both must belong to the same tenant."""
    current_user = g.current_user
    data = request.get_json(silent=True)
    if not data:
        return jsonify({'status': 'error', 'message': 'Missing request body'}), 400

    target_user = User.query.get(user_id)
    if target_user is None or target_user.tenant_id != current_user.tenant_id:
        return jsonify({'status': 'error', 'message': 'User not found'}), 404

    role_id = data.get('role_id')
    if role_id is None:
        return jsonify({'status': 'error', 'message': 'Missing role_id'}), 400

    role = Role.query.get(role_id)
    if role is None or role.tenant_id != current_user.tenant_id:
        return jsonify({'status': 'error', 'message': 'Role not found'}), 404

    # Check if already assigned; skip to avoid duplicate insert errors
    existing = db.session.execute(
        user_roles.select().where(
            user_roles.c.user_id == user_id,
            user_roles.c.role_id == role_id
        )
    ).fetchone()
    if existing is None:
        db.session.execute(user_roles.insert().values(user_id=user_id, role_id=role_id))
        db.session.commit()

    return jsonify({'status': 'ok', 'data': None}), 200


@role_bp.route('/users/<int:user_id>/roles/<int:role_id>', methods=['DELETE'])
@check_permission('role.manage')
def remove_role(user_id, role_id):
    """Remove a role from a user. Idempotent — no error if not assigned."""
    current_user = g.current_user

    target_user = User.query.get(user_id)
    if target_user is None or target_user.tenant_id != current_user.tenant_id:
        return jsonify({'status': 'error', 'message': 'User not found'}), 404

    db.session.execute(
        user_roles.delete().where(
            user_roles.c.user_id == user_id,
            user_roles.c.role_id == role_id
        )
    )
    db.session.commit()

    return jsonify({'status': 'ok', 'data': None}), 200
