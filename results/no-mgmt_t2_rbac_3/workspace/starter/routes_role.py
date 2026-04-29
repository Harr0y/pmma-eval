"""
T2 RBAC System — Role Management Routes

Role CRUD, user-role assignment, permission management.
All operations require role.manage permission.
"""

from flask import Blueprint, request, jsonify, g
from models import Role, Permission, User, user_roles as user_roles_table
from middleware import check_permission
from app import db

role_bp = Blueprint('role_bp', __name__)


def _role_to_dict(role):
    return {
        'id': role.id,
        'name': role.name,
        'parent_role_id': role.parent_role_id,
        'permissions': [p.code for p in role.permissions],
    }


def _would_create_cycle(role_id, new_parent_id):
    """Check if setting role_id's parent to new_parent_id would create a cycle."""
    if new_parent_id is None:
        return False
    visited = set()
    current = new_parent_id
    while current is not None:
        if current == role_id:
            return True
        if current in visited:
            return True
        visited.add(current)
        role = Role.query.get(current)
        if role is None:
            break
        current = role.parent_role_id
    return False


@role_bp.route('/roles', methods=['POST'])
@check_permission('role.manage')
def create_role():
    data = request.get_json(silent=True)
    if not data or not data.get('name'):
        return jsonify({'status': 'error', 'message': 'Role name is required'}), 400

    name = data['name']
    parent_role_id = data.get('parent_role_id')
    permission_codes = data.get('permissions', [])

    # Check duplicate name within same tenant
    existing = Role.query.filter_by(tenant_id=g.current_user.tenant_id, name=name).first()
    if existing:
        return jsonify({'status': 'error', 'message': 'Role name already exists'}), 409

    # Validate parent_role_id if provided
    if parent_role_id is not None:
        parent = Role.query.get(parent_role_id)
        if parent is None or parent.tenant_id != g.current_user.tenant_id:
            return jsonify({'status': 'error', 'message': 'Invalid parent role'}), 400

    # Create role
    role = Role(
        tenant_id=g.current_user.tenant_id,
        name=name,
        parent_role_id=parent_role_id,
    )
    db.session.add(role)
    db.session.flush()

    # Attach permissions
    if permission_codes:
        perms = Permission.query.filter(Permission.code.in_(permission_codes)).all()
        role.permissions = perms

    db.session.commit()
    return jsonify({'status': 'ok', 'data': _role_to_dict(role)}), 201


@role_bp.route('/roles', methods=['GET'])
@check_permission('role.manage')
def list_roles():
    roles = Role.query.filter_by(tenant_id=g.current_user.tenant_id).all()
    return jsonify({'status': 'ok', 'data': [_role_to_dict(r) for r in roles]}), 200


@role_bp.route('/roles/<int:role_id>/permissions', methods=['PUT'])
@check_permission('role.manage')
def update_role_permissions(role_id):
    role = Role.query.get(role_id)
    if role is None or role.tenant_id != g.current_user.tenant_id:
        return jsonify({'status': 'error', 'message': 'Role not found'}), 404

    data = request.get_json(silent=True)
    if data is None:
        data = {}

    permission_codes = data.get('permissions', [])
    new_parent_id = data.get('parent_role_id', role.parent_role_id)

    # Validate parent if changing
    if new_parent_id != role.parent_role_id:
        if new_parent_id is not None:
            parent = Role.query.get(new_parent_id)
            if parent is None or parent.tenant_id != g.current_user.tenant_id:
                return jsonify({'status': 'error', 'message': 'Invalid parent role'}), 400

        # Cycle detection
        if _would_create_cycle(role_id, new_parent_id):
            return jsonify({'status': 'error', 'message': 'Inheritance cycle detected'}), 400

        role.parent_role_id = new_parent_id

    # Update permissions
    if permission_codes:
        perms = Permission.query.filter(Permission.code.in_(permission_codes)).all()
        role.permissions = perms
    else:
        role.permissions = []

    db.session.commit()
    return jsonify({'status': 'ok', 'data': _role_to_dict(role)}), 200


@role_bp.route('/users/<int:user_id>/roles', methods=['POST'])
@check_permission('role.manage')
def assign_role(user_id):
    data = request.get_json(silent=True)
    if not data or not data.get('role_id'):
        return jsonify({'status': 'error', 'message': 'role_id is required'}), 400

    user = User.query.get(user_id)
    if user is None:
        return jsonify({'status': 'error', 'message': 'User not found'}), 404

    role = Role.query.get(data['role_id'])
    if role is None:
        return jsonify({'status': 'error', 'message': 'Role not found'}), 404

    # Both user and role must belong to same tenant
    if user.tenant_id != g.current_user.tenant_id or role.tenant_id != g.current_user.tenant_id:
        return jsonify({'status': 'error', 'message': 'User and role must belong to same tenant'}), 403

    # Add role if not already assigned
    if role not in user.roles:
        user.roles.append(role)
        db.session.commit()

    return jsonify({'status': 'ok', 'data': {'user_id': user.id, 'role_id': role.id}}), 200


@role_bp.route('/users/<int:user_id>/roles/<int:role_id>', methods=['DELETE'])
@check_permission('role.manage')
def remove_role(user_id, role_id):
    user = User.query.get(user_id)
    if user is None:
        return jsonify({'status': 'error', 'message': 'User not found'}), 404

    role = Role.query.get(role_id)
    if role is not None and role in user.roles:
        user.roles.remove(role)
        db.session.commit()

    return jsonify({'status': 'ok', 'data': None}), 200
