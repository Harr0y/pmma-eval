"""
T2 RBAC System -- Role Management Routes (Sample 2)

Variant strategy differences from Sample 1:
- BFS-based cycle detection using a queue (iterative, avoids recursion depth limits)
- Explicit key-presence validation with isinstance guards
- Role serialiser as a standalone helper with explicit permission list extraction
- Iterative ancestor chain traversal for cycle checks (while-loop over parent_role_id)
- Uses db.session.query() with .get() for primary-key lookups
"""

from flask import Blueprint, request, jsonify, g
from models import Role, Permission, User, role_permissions, user_roles
from middleware import check_permission
from app import db

role_bp = Blueprint('role_bp', __name__)


def _serialise_role(role):
    """Convert a Role ORM object to a plain dict for JSON responses."""
    return {
        'id': role.id,
        'name': role.name,
        'parent_role_id': role.parent_role_id,
        'permissions': [p.code for p in role.permissions],
    }


def _resolve_permissions(perm_codes):
    """Resolve a list of permission code strings to Permission ORM objects.
    Silently skips codes that do not exist in the Permission table.
    """
    if not perm_codes:
        return []
    found = Permission.query.filter(Permission.code.in_(perm_codes)).all()
    return found


def _would_create_cycle(role_id, new_parent_id):
    """BFS cycle detection: check if setting role_id's parent to new_parent_id
    would create a cycle in the inheritance chain.

    Walks UP from new_parent_id towards the root. If we encounter role_id,
    then role_id would be its own ancestor -- that is a cycle.
    """
    if new_parent_id is None or new_parent_id == role_id:
        return new_parent_id == role_id

    visited = set()
    queue = [new_parent_id]
    while queue:
        current_id = queue.pop(0)
        if current_id == role_id:
            return True
        if current_id in visited:
            continue
        visited.add(current_id)
        current_role = Role.query.get(current_id)
        if current_role and current_role.parent_role_id is not None:
            queue.append(current_role.parent_role_id)
    return False


def _get_tenant_roles(tenant_id):
    """Fetch all roles belonging to a given tenant."""
    return Role.query.filter_by(tenant_id=tenant_id).all()


# ---- POST /roles: Create a new role ----

@role_bp.route('/roles', methods=['POST'])
@check_permission('role.manage')
def create_role():
    body = request.get_json(silent=True)
    if not isinstance(body, dict):
        return jsonify({'status': 'error', 'message': 'Request body must be JSON'}), 400

    name = body.get('name')
    if not name or not isinstance(name, str):
        return jsonify({'status': 'error', 'message': 'name is required'}), 400

    perm_codes = body.get('permissions')
    if not isinstance(perm_codes, list):
        perm_codes = []

    parent_role_id = body.get('parent_role_id')
    user = g.current_user

    # Check duplicate name within same tenant
    existing = Role.query.filter_by(tenant_id=user.tenant_id, name=name).first()
    if existing:
        return jsonify({'status': 'error', 'message': 'Role name already exists in this tenant'}), 409

    # Validate parent_role_id belongs to same tenant
    if parent_role_id is not None:
        parent = Role.query.get(parent_role_id)
        if parent is None or parent.tenant_id != user.tenant_id:
            return jsonify({'status': 'error', 'message': 'Invalid parent role'}), 400

    # Create the role first so we have an ID for cycle check
    role = Role(tenant_id=user.tenant_id, name=name, parent_role_id=parent_role_id)
    db.session.add(role)
    db.session.flush()  # get role.id

    # Check for inheritance cycle after the role has an ID
    if parent_role_id is not None and _would_create_cycle(role.id, parent_role_id):
        db.session.rollback()
        return jsonify({'status': 'error', 'message': 'Inheritance cycle detected'}), 400

    # Attach permissions
    perms = _resolve_permissions(perm_codes)
    role.permissions = perms

    db.session.commit()
    return jsonify({'status': 'ok', 'data': _serialise_role(role)}), 201


# ---- GET /roles: List roles for current tenant ----

@role_bp.route('/roles', methods=['GET'])
@check_permission('role.manage')
def list_roles():
    user = g.current_user
    roles = _get_tenant_roles(user.tenant_id)
    return jsonify({'status': 'ok', 'data': [_serialise_role(r) for r in roles]}), 200


# ---- PUT /roles/<id>/permissions: Update permissions and parent ----

@role_bp.route('/roles/<int:role_id>/permissions', methods=['PUT'])
@check_permission('role.manage')
def update_role_permissions(role_id):
    role = Role.query.get(role_id)
    if role is None:
        return jsonify({'status': 'error', 'message': 'Role not found'}), 404

    user = g.current_user
    if role.tenant_id != user.tenant_id:
        return jsonify({'status': 'error', 'message': 'Role not found'}), 404

    body = request.get_json(silent=True)
    if not isinstance(body, dict):
        return jsonify({'status': 'error', 'message': 'Request body must be JSON'}), 400

    new_parent_id = body.get('parent_role_id')
    perm_codes = body.get('permissions')
    if not isinstance(perm_codes, list):
        perm_codes = []

    # Validate parent if provided
    if new_parent_id is not None:
        parent = Role.query.get(new_parent_id)
        if parent is None or parent.tenant_id != user.tenant_id:
            return jsonify({'status': 'error', 'message': 'Invalid parent role'}), 400

    # Cycle detection
    if _would_create_cycle(role_id, new_parent_id):
        return jsonify({'status': 'error', 'message': 'Inheritance cycle detected'}), 400

    role.parent_role_id = new_parent_id
    role.permissions = _resolve_permissions(perm_codes)
    db.session.commit()

    return jsonify({'status': 'ok', 'data': _serialise_role(role)}), 200


# ---- POST /users/<id>/roles: Assign a role to a user ----

@role_bp.route('/users/<int:user_id>/roles', methods=['POST'])
@check_permission('role.manage')
def assign_role_to_user(user_id):
    target_user = User.query.get(user_id)
    if target_user is None:
        return jsonify({'status': 'error', 'message': 'User not found'}), 404

    body = request.get_json(silent=True)
    if not isinstance(body, dict):
        return jsonify({'status': 'error', 'message': 'Request body must be JSON'}), 400

    role_id = body.get('role_id')
    if not isinstance(role_id, int):
        return jsonify({'status': 'error', 'message': 'role_id is required'}), 400

    role = Role.query.get(role_id)
    if role is None:
        return jsonify({'status': 'error', 'message': 'Role not found'}), 404

    # Cross-tenant check: both user and role must belong to same tenant
    if target_user.tenant_id != role.tenant_id:
        return jsonify({'status': 'error', 'message': 'User and role must belong to same tenant'}), 403

    # Assign if not already assigned
    if role not in target_user.roles:
        target_user.roles.append(role)
        db.session.commit()

    return jsonify({'status': 'ok', 'data': _serialise_role(role)}), 200


# ---- DELETE /users/<id>/roles/<role_id>: Remove role from user ----

@role_bp.route('/users/<int:user_id>/roles/<int:role_id>', methods=['DELETE'])
@check_permission('role.manage')
def remove_role_from_user(user_id, role_id):
    target_user = User.query.get(user_id)
    if target_user is None:
        return jsonify({'status': 'error', 'message': 'User not found'}), 404

    role = Role.query.get(role_id)
    if role is not None and role in target_user.roles:
        target_user.roles.remove(role)
        db.session.commit()

    # Idempotent: no error if role was not assigned
    return jsonify({'status': 'ok', 'data': None}), 200
