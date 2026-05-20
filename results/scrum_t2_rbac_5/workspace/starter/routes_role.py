"""
T2 RBAC System — Role Management Routes

Role CRUD, user-role assignment, permission management.
Register as a Flask Blueprint named 'role_bp'.
All operations require role.manage permission.
"""

from flask import Blueprint, request, jsonify, g

role_bp = Blueprint('role_bp', __name__)

from models import Role, Permission, User, role_permissions, user_roles
from middleware import check_permission
from app import db


def _would_create_cycle(role_id, new_parent_id):
    """Check if setting role_id's parent to new_parent_id would create a cycle."""
    visited = set()
    current = new_parent_id
    while current is not None:
        if current == role_id:
            return True
        if current in visited:
            return False
        visited.add(current)
        parent = Role.query.get(current)
        if parent is None:
            break
        current = parent.parent_role_id
    return False


def _resolve_permissions(perm_codes):
    """Given a list of permission code strings, return a list of Permission objects.
    Creates Permission records that don't yet exist."""
    result = []
    for code in perm_codes:
        perm = Permission.query.filter_by(code=code).first()
        if perm is None:
            perm = Permission(code=code)
            db.session.add(perm)
        result.append(perm)
    return result


def _role_dict(role):
    """Serialize a role to a dict including its permission codes."""
    return {
        'id': role.id,
        'name': role.name,
        'parent_role_id': role.parent_role_id,
        'permissions': [p.code for p in role.permissions],
    }


@role_bp.route('/roles', methods=['POST'])
@check_permission('role.manage')
def create_role():
    """Create a new role in the current tenant."""
    data = request.get_json()
    if not data or 'name' not in data:
        return jsonify({'status': 'error', 'message': 'Name is required'}), 400

    user = g.current_user
    name = data['name']
    parent_role_id = data.get('parent_role_id')
    perm_codes = data.get('permissions', [])

    # Validate parent role belongs to same tenant
    if parent_role_id is not None:
        parent = Role.query.get(parent_role_id)
        if parent is None or parent.tenant_id != user.tenant_id:
            return jsonify({'status': 'error', 'message': 'Invalid parent role'}), 400

    role = Role(tenant_id=user.tenant_id, name=name, parent_role_id=parent_role_id)
    db.session.add(role)
    db.session.flush()  # Get role.id

    # Set permissions
    perms = _resolve_permissions(perm_codes)
    for perm in perms:
        db.session.execute(
            role_permissions.insert().values(role_id=role.id, permission_id=perm.id)
        )

    db.session.commit()
    db.session.refresh(role)
    return jsonify({'status': 'ok', 'data': _role_dict(role)}), 201


@role_bp.route('/roles', methods=['GET'])
@check_permission('role.manage')
def list_roles():
    """List all roles for the current tenant."""
    user = g.current_user
    roles = Role.query.filter_by(tenant_id=user.tenant_id).all()
    return jsonify({'status': 'ok', 'data': [_role_dict(r) for r in roles]}), 200


@role_bp.route('/roles/<int:role_id>/permissions', methods=['PUT'])
@check_permission('role.manage')
def update_role_permissions(role_id):
    """Replace permission set and/or update parent for a role."""
    user = g.current_user
    role = Role.query.get(role_id)
    if role is None or role.tenant_id != user.tenant_id:
        return jsonify({'status': 'error', 'message': 'Role not found'}), 404

    data = request.get_json()
    if data is None:
        data = {}

    parent_role_id = data.get('parent_role_id', role.parent_role_id)
    perm_codes = data.get('permissions', None)

    # Validate parent role
    if parent_role_id is not None:
        parent = Role.query.get(parent_role_id)
        if parent is None or parent.tenant_id != user.tenant_id:
            return jsonify({'status': 'error', 'message': 'Invalid parent role'}), 400

        # Cycle detection
        if _would_create_cycle(role.id, parent_role_id):
            return jsonify({'status': 'error', 'message': 'Inheritance cycle detected'}), 400

    # Update parent
    role.parent_role_id = parent_role_id

    # Replace permissions if provided
    if perm_codes is not None:
        db.session.execute(
            role_permissions.delete().where(role_permissions.c.role_id == role.id)
        )
        perms = _resolve_permissions(perm_codes)
        for perm in perms:
            db.session.execute(
                role_permissions.insert().values(role_id=role.id, permission_id=perm.id)
            )

    db.session.commit()
    db.session.refresh(role)
    return jsonify({'status': 'ok', 'data': _role_dict(role)}), 200


@role_bp.route('/users/<int:user_id>/roles', methods=['POST'])
@check_permission('role.manage')
def assign_role(user_id):
    """Assign a role to a user. Both must belong to the same tenant."""
    data = request.get_json()
    if not data or 'role_id' not in data:
        return jsonify({'status': 'error', 'message': 'role_id is required'}), 400

    current_user = g.current_user
    target_user = User.query.get(user_id)
    if target_user is None:
        return jsonify({'status': 'error', 'message': 'User not found'}), 404

    role = Role.query.get(data['role_id'])
    if role is None or role.tenant_id != current_user.tenant_id:
        return jsonify({'status': 'error', 'message': 'Role not found'}), 404

    # Cross-tenant check: target user must be in the same tenant as the acting user
    if target_user.tenant_id != current_user.tenant_id:
        return jsonify({'status': 'error', 'message': 'Forbidden'}), 403

    db.session.execute(
        user_roles.insert().values(user_id=user_id, role_id=role.id)
    )
    db.session.commit()
    return jsonify({'status': 'ok', 'data': {'user_id': user_id, 'role_id': role.id}}), 200


@role_bp.route('/users/<int:user_id>/roles/<int:role_id>', methods=['DELETE'])
@check_permission('role.manage')
def remove_role(user_id, role_id):
    """Remove a role from a user. Idempotent."""
    user = User.query.get(user_id)
    if user is None:
        return jsonify({'status': 'error', 'message': 'User not found'}), 404

    db.session.execute(
        user_roles.delete().where(
            (user_roles.c.user_id == user_id) & (user_roles.c.role_id == role_id)
        )
    )
    db.session.commit()
    return jsonify({'status': 'ok', 'data': {'user_id': user_id, 'role_id': role_id}}), 200
