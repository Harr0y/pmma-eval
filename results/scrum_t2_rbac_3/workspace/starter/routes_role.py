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
from middleware import get_current_user, check_permission, get_user_permissions
from app import db
from models import User, Role, Permission, role_permissions, user_roles

role_bp = Blueprint('role_bp', __name__)


def _role_to_dict(role):
    """Serialize a role to a dict including its permission codes."""
    return {
        'id': role.id,
        'name': role.name,
        'parent_role_id': role.parent_role_id,
        'permissions': [p.code for p in role.permissions],
    }


def _has_cycle(role_id, new_parent_id):
    """Check if setting new_parent_id as parent of role_id creates a cycle.

    Walks up from new_parent_id to see if it eventually reaches role_id.
    """
    visited = set()
    current = new_parent_id
    while current is not None:
        if current == role_id:
            return True
        if current in visited:
            return True  # unexpected loop in existing data
        visited.add(current)
        parent_role = Role.query.get(current)
        if parent_role is None:
            break
        current = parent_role.parent_role_id
    return False


@role_bp.route('/roles', methods=['POST'])
@check_permission('role.manage')
def create_role():
    """Create a new role in the current user's tenant."""
    user = g.current_user
    data = request.get_json(silent=True) or {}

    name = data.get('name')
    if not name:
        return jsonify({'status': 'error', 'message': 'Missing name'}), 400

    permissions = data.get('permissions', [])
    parent_role_id = data.get('parent_role_id')

    # Check duplicate name within same tenant
    existing = Role.query.filter_by(tenant_id=user.tenant_id, name=name).first()
    if existing:
        return jsonify({'status': 'error', 'message': 'Role name already exists in this tenant'}), 409

    # Validate parent role if provided
    if parent_role_id is not None:
        parent = Role.query.get(parent_role_id)
        if parent is None or parent.tenant_id != user.tenant_id:
            return jsonify({'status': 'error', 'message': 'Invalid parent role'}), 400

    # Create the role
    role = Role(tenant_id=user.tenant_id, name=name, parent_role_id=parent_role_id)
    db.session.add(role)
    db.session.flush()  # get role.id

    # Attach permissions by code
    if permissions:
        perm_objects = Permission.query.filter(Permission.code.in_(permissions)).all()
        role.permissions = perm_objects

    db.session.commit()

    return jsonify({'status': 'ok', 'data': _role_to_dict(role)}), 201


@role_bp.route('/roles', methods=['GET'])
@check_permission('role.manage')
def list_roles():
    """List all roles for the current user's tenant."""
    user = g.current_user
    roles = Role.query.filter_by(tenant_id=user.tenant_id).all()
    return jsonify({'status': 'ok', 'data': [_role_to_dict(r) for r in roles]})


@role_bp.route('/roles/<int:role_id>/permissions', methods=['PUT'])
@check_permission('role.manage')
def update_role_permissions(role_id):
    """Replace role permissions and/or update parent role.

    Detects inheritance cycles when setting parent_role_id.
    """
    user = g.current_user
    role = Role.query.get(role_id)

    if role is None or role.tenant_id != user.tenant_id:
        return jsonify({'status': 'error', 'message': 'Role not found'}), 404

    data = request.get_json(silent=True) or {}
    new_permissions = data.get('permissions', None)
    new_parent_id = data.get('parent_role_id', None)

    # If parent_role_id is provided (not missing from request), validate it
    if 'parent_role_id' in data:
        if new_parent_id is not None:
            parent = Role.query.get(new_parent_id)
            if parent is None or parent.tenant_id != user.tenant_id:
                return jsonify({'status': 'error', 'message': 'Invalid parent role'}), 400

            # Cycle detection: would new_parent_id as parent create a cycle?
            if _has_cycle(role_id, new_parent_id):
                return jsonify({'status': 'error', 'message': 'Inheritance cycle detected'}), 400

        role.parent_role_id = new_parent_id

    # Replace permissions if provided
    if new_permissions is not None:
        perm_objects = Permission.query.filter(Permission.code.in_(new_permissions)).all()
        role.permissions = perm_objects

    db.session.commit()

    return jsonify({'status': 'ok', 'data': _role_to_dict(role)})


@role_bp.route('/users/<int:user_id>/roles', methods=['POST'])
@check_permission('role.manage')
def assign_role_to_user(user_id):
    """Assign a role to a user. Both must be in the same tenant."""
    user = g.current_user
    target_user = User.query.get(user_id)

    if target_user is None:
        return jsonify({'status': 'error', 'message': 'User not found'}), 404

    data = request.get_json(silent=True) or {}
    role_id = data.get('role_id')

    if role_id is None:
        return jsonify({'status': 'error', 'message': 'Missing role_id'}), 400

    role = Role.query.get(role_id)

    if role is None:
        return jsonify({'status': 'error', 'message': 'Role not found'}), 404

    # Both user and role must belong to the same tenant
    if target_user.tenant_id != role.tenant_id:
        return jsonify({'status': 'error', 'message': 'User and role must be in the same tenant'}), 404

    # Check if already assigned
    existing = db.session.query(user_roles).filter_by(
        user_id=user_id, role_id=role_id
    ).first()

    if not existing:
        db.session.execute(user_roles.insert().values(user_id=user_id, role_id=role_id))
        db.session.commit()

    return jsonify({'status': 'ok', 'data': {'user_id': user_id, 'role_id': role_id}})


@role_bp.route('/users/<int:user_id>/roles/<int:role_id>', methods=['DELETE'])
@check_permission('role.manage')
def remove_role_from_user(user_id, role_id):
    """Remove a role from a user. Idempotent -- no error if not assigned."""
    user = g.current_user
    target_user = User.query.get(user_id)

    if target_user is None:
        return jsonify({'status': 'error', 'message': 'User not found'}), 404

    db.session.execute(
        user_roles.delete().where(
            user_roles.c.user_id == user_id,
            user_roles.c.role_id == role_id,
        )
    )
    db.session.commit()

    return jsonify({'status': 'ok', 'data': {'user_id': user_id, 'role_id': role_id}})
