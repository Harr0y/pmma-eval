"""
T2 RBAC System — Role Management Routes

Role CRUD, user-role assignment, and inheritance chain cycle detection.
Register as a Flask Blueprint named 'role_bp'.
All operations require role.manage permission.

Requirements:
- POST /roles -> Create role (same-tenant name uniqueness, parent validation)
- GET /roles -> List roles for current tenant
- PUT /roles/<id>/permissions -> Replace permissions + update parent + cycle detection
- POST /users/<id>/roles -> Assign role (user and role must be same tenant)
- DELETE /users/<id>/roles/<role_id> -> Remove role (idempotent)

IMPORTANT: Role inheritance is handled by middleware._collect_role_permissions().
Roles are tenant-scoped. This module works with middleware.py and routes_document.py.
"""

from flask import Blueprint, request, jsonify, g
from models import Role, Permission, User, user_roles, role_permissions
from middleware import check_permission
from app import db

role_bp = Blueprint('role_bp', __name__)


def _would_create_cycle(role_id, new_parent_id):
    """Check whether setting role_id's parent to new_parent_id would create a cycle.

    Algorithm: Starting from new_parent_id, walk up the parent_role_id chain.
    If we encounter role_id during the traversal, a cycle would be formed.

    Example: A -> B -> C (C's parent is B)
    If we try to set B's parent to C, traversal from C: C -> B -> ... finds B (=role_id),
    so this would create a cycle: B -> C -> B.

    Returns:
        True: a cycle would be created
        False: safe to proceed
    """
    visited = set()
    current = new_parent_id
    while current is not None:
        if current == role_id:
            return True
        if current in visited:
            return True  # defensive check for pre-existing cycle
        visited.add(current)
        parent_role = Role.query.get(current)
        if parent_role is None:
            break
        current = parent_role.parent_role_id
    return False


def _serialize_role(role):
    """Serialize a Role model instance to a JSON-serializable dict."""
    return {
        "id": role.id,
        "name": role.name,
        "parent_role_id": role.parent_role_id,
        "permissions": [p.code for p in role.permissions],
    }


@role_bp.route('/roles', methods=['POST'])
@check_permission('role.manage')
def create_role():
    """Create a new role within the current user's tenant.

    Validates:
    - 'name' is required and non-empty
    - Role name must be unique within the tenant (409 on duplicate)
    - parent_role_id (if provided) must belong to the same tenant (400 otherwise)

    Permissions are resolved from Permission.code and attached to the new role.
    Returns 201 on success.
    """
    user = g.current_user
    data = request.get_json(silent=True)
    if data is None:
        return jsonify({"status": "error", "message": "Request must be JSON"}), 400

    name = data.get('name')
    if not name:
        return jsonify({"status": "error", "message": "Name is required"}), 400

    # Same-tenant role name uniqueness
    existing = Role.query.filter_by(tenant_id=user.tenant_id, name=name).first()
    if existing:
        return jsonify({"status": "error", "message": "Role name already exists"}), 409

    # Validate parent_role_id belongs to same tenant
    parent_id = data.get('parent_role_id')
    if parent_id is not None:
        parent = Role.query.get(parent_id)
        if parent is None or parent.tenant_id != user.tenant_id:
            return jsonify({"status": "error", "message": "Invalid parent role"}), 400

    # Create role
    role = Role(tenant_id=user.tenant_id, name=name, parent_role_id=parent_id)
    db.session.add(role)
    db.session.flush()  # obtain role.id

    # Attach permissions by code lookup
    perm_codes = data.get('permissions', [])
    for code in perm_codes:
        perm = Permission.query.filter_by(code=code).first()
        if perm:
            role.permissions.append(perm)

    db.session.commit()
    return jsonify({"status": "ok", "data": _serialize_role(role)}), 201


@role_bp.route('/roles', methods=['GET'])
@check_permission('role.manage')
def list_roles():
    """List all roles belonging to the current user's tenant.

    Each role includes its id, name, parent_role_id, and associated
    permission codes.
    """
    user = g.current_user
    roles = Role.query.filter_by(tenant_id=user.tenant_id).all()
    return jsonify({"status": "ok", "data": [_serialize_role(r) for r in roles]}), 200


@role_bp.route('/roles/<int:role_id>/permissions', methods=['PUT'])
@check_permission('role.manage')
def update_role_permissions(role_id):
    """Replace a role's permission set and optionally update its parent role.

    Validates:
    - Role must exist and belong to the current user's tenant (404 otherwise)
    - parent_role_id (if provided) must belong to same tenant (400 otherwise)
    - Setting parent must not create an inheritance cycle (400 otherwise)

    Permissions are fully replaced (not merged): existing permissions are
    cleared, then new ones are attached from the request body.
    """
    user = g.current_user
    role = Role.query.get(role_id)
    if role is None or role.tenant_id != user.tenant_id:
        return jsonify({"status": "error", "message": "Role not found"}), 404

    data = request.get_json(silent=True)
    if data is None:
        return jsonify({"status": "error", "message": "Request must be JSON"}), 400

    # Validate and set parent_role_id
    parent_id = data.get('parent_role_id')
    if parent_id is not None:
        parent = Role.query.get(parent_id)
        if parent is None or parent.tenant_id != user.tenant_id:
            return jsonify({"status": "error", "message": "Invalid parent role"}), 400
        # Cycle detection
        if _would_create_cycle(role.id, parent_id):
            return jsonify({"status": "error", "message": "Inheritance cycle detected"}), 400
    role.parent_role_id = parent_id

    # Replace permission set
    role.permissions = []
    perm_codes = data.get('permissions', [])
    for code in perm_codes:
        perm = Permission.query.filter_by(code=code).first()
        if perm:
            role.permissions.append(perm)

    db.session.commit()
    return jsonify({"status": "ok", "data": _serialize_role(role)}), 200


@role_bp.route('/users/<int:user_id>/roles', methods=['POST'])
@check_permission('role.manage')
def assign_role(user_id):
    """Assign a role to a user.

    Both the target user and the role must belong to the current user's tenant.
    Duplicate assignments are silently ignored (no error, no extra DB write).

    Returns 200 with user_id and role_id on success.
    """
    current = g.current_user
    target_user = User.query.get(user_id)
    if target_user is None or target_user.tenant_id != current.tenant_id:
        return jsonify({"status": "error", "message": "User not found"}), 404

    data = request.get_json(silent=True)
    if data is None:
        return jsonify({"status": "error", "message": "Request must be JSON"}), 400

    role = Role.query.get(data.get('role_id'))
    if role is None or role.tenant_id != current.tenant_id:
        return jsonify({"status": "error", "message": "Role not found"}), 404

    # Avoid duplicate assignment
    if role not in target_user.roles:
        target_user.roles.append(role)
        db.session.commit()

    return jsonify({"status": "ok", "data": {"user_id": user_id, "role_id": role.id}}), 200


@role_bp.route('/users/<int:user_id>/roles/<int:role_id>', methods=['DELETE'])
@check_permission('role.manage')
def remove_role(user_id, role_id):
    """Remove a role from a user.

    Idempotent: if the user does not have the specified role, the operation
    still succeeds with 200 (no error raised).

    Returns 200 with user_id and role_id.
    """
    current = g.current_user
    target_user = User.query.get(user_id)
    if target_user is None or target_user.tenant_id != current.tenant_id:
        return jsonify({"status": "error", "message": "User not found"}), 404

    role = Role.query.get(role_id)
    if role and role in target_user.roles:
        target_user.roles.remove(role)
        db.session.commit()

    # Idempotent: no error if role was not assigned
    return jsonify({"status": "ok", "data": {"user_id": user_id, "role_id": role_id}}), 200
