"""
T2 RBAC System — Role Management Routes

Role CRUD, user-role assignment, permission management.
Register as a Flask Blueprint named 'role_bp'.
All operations require role.manage permission.

Endpoints:
- POST /roles                          -> Create role (design.md 4.7)
- GET /roles                           -> List roles for current tenant (design.md 4.8)
- PUT /roles/<id>/permissions           -> Update role permissions/parent (design.md 4.9)
- POST /users/<id>/roles                -> Assign role to user (design.md 4.10)
- DELETE /users/<id>/roles/<role_id>    -> Remove role from user (design.md 4.11)
"""

from flask import Blueprint, request, jsonify, g
from models import Role, Permission, User
from middleware import check_permission
from app import db

role_bp = Blueprint('role_bp', __name__)


def _serialize_role(role):
    """Serialize a Role model instance to a dict (design.md 5.4)."""
    return {
        'id': role.id,
        'name': role.name,
        'parent_role_id': role.parent_role_id,
        'permissions': [p.code for p in role.permissions],
    }


def _has_cycle(role_id, target_parent_id):
    """Check if setting role_id's parent to target_parent_id would create a cycle.
    Walks up the inheritance chain from target_parent_id; if we encounter role_id,
    a cycle exists. (design.md 5.1)"""
    visited = set()
    current = target_parent_id
    while current is not None:
        if current == role_id:
            return True
        if current in visited:
            return True  # pre-existing cycle in DB
        visited.add(current)
        role = Role.query.get(current)
        if role is None:
            return False
        current = role.parent_role_id
    return False


# --- design.md 4.7: POST /roles ---
@role_bp.route('/roles', methods=['POST'])
@check_permission('role.manage')
def create_role():
    """Create a new role for the current tenant."""
    data = request.get_json(silent=True)
    if data is None:
        return jsonify({'status': 'error', 'message': 'Request must be JSON'}), 400

    name = data.get('name')
    if not name:
        return jsonify({'status': 'error', 'message': 'name is required'}), 400

    parent_role_id = data.get('parent_role_id')
    permissions = data.get('permissions', [])

    # Check duplicate role name within same tenant
    existing = Role.query.filter_by(tenant_id=g.current_user.tenant_id, name=name).first()
    if existing:
        return jsonify({'status': 'error', 'message': 'Role name already exists in this tenant'}), 409

    # Validate parent_role_id if provided
    if parent_role_id is not None:
        parent_role = Role.query.get(parent_role_id)
        if parent_role is None:
            return jsonify({'status': 'error', 'message': 'Parent role not found'}), 400
        if parent_role.tenant_id != g.current_user.tenant_id:
            return jsonify({'status': 'error', 'message': 'Parent role not found'}), 404

    # Create role
    role = Role(tenant_id=g.current_user.tenant_id, name=name, parent_role_id=parent_role_id)

    # Associate permissions (full replace via assignment)
    perm_objects = Permission.query.filter(Permission.code.in_(permissions)).all()
    role.permissions = perm_objects

    db.session.add(role)
    db.session.commit()

    return jsonify({'status': 'ok', 'data': _serialize_role(role)}), 201


# --- design.md 4.8: GET /roles ---
@role_bp.route('/roles', methods=['GET'])
@check_permission('role.manage')
def list_roles():
    """List all roles for the current user's tenant."""
    roles = Role.query.filter_by(tenant_id=g.current_user.tenant_id).all()
    return jsonify({'status': 'ok', 'data': [_serialize_role(r) for r in roles]}), 200


# --- design.md 4.9: PUT /roles/<id>/permissions ---
@role_bp.route('/roles/<int:id>/permissions', methods=['PUT'])
@check_permission('role.manage')
def update_role_permissions(id):
    """Update a role's permissions and/or parent_role_id.
    permissions field uses full-replacement semantics."""
    role = Role.query.get(id)
    if role is None:
        return jsonify({'status': 'error', 'message': 'Role not found'}), 404

    # Tenant isolation check
    if role.tenant_id != g.current_user.tenant_id:
        return jsonify({'status': 'error', 'message': 'Role not found'}), 404

    data = request.get_json(silent=True)
    if data is None:
        return jsonify({'status': 'error', 'message': 'Request must be JSON'}), 400

    new_permissions = data.get('permissions', None)

    # Handle parent_role_id update if provided (distinguish "not provided" from "explicitly null")
    if 'parent_role_id' in data:
        parent_role_id = data['parent_role_id']
        if parent_role_id is not None:
            # Self-reference check
            if parent_role_id == id:
                return jsonify({'status': 'error', 'message': 'Circular role inheritance detected'}), 400

            parent_role = Role.query.get(parent_role_id)
            if parent_role is None:
                return jsonify({'status': 'error', 'message': 'Parent role not found'}), 400
            if parent_role.tenant_id != g.current_user.tenant_id:
                return jsonify({'status': 'error', 'message': 'Parent role not found'}), 400

            # Cycle detection
            if _has_cycle(id, parent_role_id):
                return jsonify({'status': 'error', 'message': 'Circular role inheritance detected'}), 400

            role.parent_role_id = parent_role_id
        else:
            role.parent_role_id = None

    # Handle permissions update if provided (full replacement semantics)
    if new_permissions is not None:
        perm_objects = Permission.query.filter(Permission.code.in_(new_permissions)).all()
        role.permissions = perm_objects

    db.session.commit()
    return jsonify({'status': 'ok', 'data': _serialize_role(role)}), 200


# --- design.md 4.10: POST /users/<id>/roles ---
@role_bp.route('/users/<int:user_id>/roles', methods=['POST'])
@check_permission('role.manage')
def assign_role_to_user(user_id):
    """Assign a role to a user. Both must belong to the same tenant."""
    user = User.query.get(user_id)
    if user is None:
        return jsonify({'status': 'error', 'message': 'User not found'}), 404

    # Tenant isolation check
    if user.tenant_id != g.current_user.tenant_id:
        return jsonify({'status': 'error', 'message': 'User not found'}), 404

    data = request.get_json(silent=True)
    if data is None:
        return jsonify({'status': 'error', 'message': 'Request must be JSON'}), 400

    role_id = data.get('role_id')
    if role_id is None:
        return jsonify({'status': 'error', 'message': 'role_id is required'}), 400

    role = Role.query.get(role_id)
    if role is None:
        return jsonify({'status': 'error', 'message': 'Role not found'}), 404

    # Tenant check on role
    if role.tenant_id != g.current_user.tenant_id:
        return jsonify({'status': 'error', 'message': 'Role not found'}), 404

    user.roles.append(role)
    db.session.commit()

    return jsonify({'status': 'ok', 'data': {'user_id': user.id, 'role_id': role.id}}), 200


# --- design.md 4.11: DELETE /users/<id>/roles/<role_id> ---
@role_bp.route('/users/<int:user_id>/roles/<int:role_id>', methods=['DELETE'])
@check_permission('role.manage')
def remove_role_from_user(user_id, role_id):
    """Remove a role from a user. Idempotent — no error if role not assigned."""
    user = User.query.get(user_id)
    if user is None:
        return jsonify({'status': 'error', 'message': 'User not found'}), 404

    # Tenant isolation check
    if user.tenant_id != g.current_user.tenant_id:
        return jsonify({'status': 'error', 'message': 'User not found'}), 404

    role = Role.query.get(role_id)
    if role is not None:
        if role.tenant_id != g.current_user.tenant_id:
            return jsonify({'status': 'error', 'message': 'Role not found'}), 404
        if role in user.roles:
            user.roles.remove(role)

    db.session.commit()

    return jsonify({'status': 'ok', 'data': {'user_id': user.id, 'role_id': role_id}}), 200
