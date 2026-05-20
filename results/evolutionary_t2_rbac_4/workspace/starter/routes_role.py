"""
T2 RBAC System — Role Management Routes (Sample 2: Inline-Auth BFS Variant)

Role CRUD, user-role assignment, permission management.
Register as a Flask Blueprint named 'role_bp'.

Design decisions (evolutionary variant):
- Manual inline auth: every route function calls middleware.get_current_user()
  and middleware.get_user_permissions() directly, then checks for 'role.manage'
  in the permission set. No decorator wrappers -- the auth + permission check
  is two lines at the top of each handler, keeping the call-site explicit and
  easy to audit.
- Monolithic route bodies: all business logic lives inside the route function
  itself. No extracted helper functions for cycle detection, serialization, or
  validation. This maximises local readability -- every route is self-contained.
- Iterative BFS cycle detection: when setting parent_role_id we walk upward
  from the proposed parent using a queue, collecting every ancestor. If the
  role being updated appears in that ancestor set we reject with 400.
- ORM relationship operations for user-role assignment: we use
  user.roles.append() / .remove() instead of raw SQL on the association table.
  SQLAlchemy handles the join-row lifecycle automatically.
- Early-return validation pattern (inherited from ATU): each validation step
  returns immediately on failure so the happy path stays at minimal indentation.

All operations require role.manage permission.
"""

from collections import deque

from flask import Blueprint, request, jsonify

from models import Role, Permission, User, role_permissions
from middleware import get_current_user, get_user_permissions
from app import db

role_bp = Blueprint('role_bp', __name__)


# ------------------------------------------------------------------
# 1. POST /roles — Create Role
# ------------------------------------------------------------------

@role_bp.route('/roles', methods=['POST'])
def create_role():
    """Create a new role within the current user's tenant.

    Request JSON:
        {"name": str, "parent_role_id": int|null, "permissions": [str, ...]}

    Success (201):
        {"status": "ok", "data": {"id": int, "name": str, "parent_role_id": int|null,
         "permissions": [str, ...]}}

    Errors:
        401 — missing / invalid token
        403 — user lacks role.manage
        400 — missing name, invalid parent, parent from another tenant
        409 — duplicate role name within same tenant
    """
    # --- Auth + permission check (inline, no decorator) ---
    user, error = get_current_user()
    if error:
        return error

    perms = get_user_permissions(user)
    if 'role.manage' not in perms:
        return jsonify({'status': 'error', 'message': 'Permission denied'}), 403

    # --- Validate request body ---
    body = request.get_json(silent=True)
    if body is None or not isinstance(body, dict):
        return jsonify({'status': 'error', 'message': 'Invalid request body'}), 400

    name = body.get('name')
    if not name or not isinstance(name, str) or not name.strip():
        return jsonify({'status': 'error', 'message': 'Missing role name'}), 400

    parent_role_id = body.get('parent_role_id')
    permission_codes = body.get('permissions', [])
    if not isinstance(permission_codes, list):
        return jsonify({'status': 'error', 'message': 'Invalid permissions format'}), 400

    tenant_id = user.tenant_id

    # --- Duplicate name check within same tenant ---
    existing = Role.query.filter_by(tenant_id=tenant_id, name=name.strip()).first()
    if existing is not None:
        return jsonify({'status': 'error', 'message': 'Role name already exists in this tenant'}), 409

    # --- Validate parent_role_id ---
    parent = None
    if parent_role_id is not None:
        parent = db.session.get(Role, parent_role_id)
        if parent is None:
            return jsonify({'status': 'error', 'message': 'Parent role not found'}), 400
        if parent.tenant_id != tenant_id:
            return jsonify({'status': 'error', 'message': 'Parent role must belong to the same tenant'}), 400

    # --- Resolve permission objects ---
    perm_objects = []
    if permission_codes:
        perm_objects = Permission.query.filter(Permission.code.in_(permission_codes)).all()

    # --- Create role ---
    role = Role(
        tenant_id=tenant_id,
        name=name.strip(),
        parent_role_id=parent_role_id,
    )
    role.permissions = perm_objects
    db.session.add(role)
    db.session.commit()

    return jsonify({
        'status': 'ok',
        'data': {
            'id': role.id,
            'name': role.name,
            'parent_role_id': role.parent_role_id,
            'permissions': [p.code for p in role.permissions],
        },
    }), 201


# ------------------------------------------------------------------
# 2. GET /roles — List Roles
# ------------------------------------------------------------------

@role_bp.route('/roles', methods=['GET'])
def list_roles():
    """List all roles for the current user's tenant.

    Success (200):
        {"status": "ok", "data": [{"id": int, "name": str, "parent_role_id": int|null,
         "permissions": [str, ...]}, ...]}

    Errors:
        401 — missing / invalid token
        403 — user lacks role.manage
    """
    # --- Auth + permission check ---
    user, error = get_current_user()
    if error:
        return error

    perms = get_user_permissions(user)
    if 'role.manage' not in perms:
        return jsonify({'status': 'error', 'message': 'Permission denied'}), 403

    # --- Query roles scoped to tenant ---
    roles = Role.query.filter_by(tenant_id=user.tenant_id).all()

    data = []
    for role in roles:
        data.append({
            'id': role.id,
            'name': role.name,
            'parent_role_id': role.parent_role_id,
            'permissions': [p.code for p in role.permissions],
        })

    return jsonify({'status': 'ok', 'data': data}), 200


# ------------------------------------------------------------------
# 3. PUT /roles/<id>/permissions — Update Permissions & Parent
# ------------------------------------------------------------------

@role_bp.route('/roles/<int:role_id>/permissions', methods=['PUT'])
def update_role_permissions(role_id):
    """Replace a role's permission set and optionally change its parent.

    Request JSON:
        {"permissions": [str, ...], "parent_role_id": int|null}

    Success (200):
        {"status": "ok", "data": {"id": int, "name": str, "parent_role_id": int|null,
         "permissions": [str, ...]}}

    Errors:
        401 — missing / invalid token
        403 — user lacks role.manage
        404 — role not found or belongs to another tenant
        400 — inheritance cycle detected, parent from another tenant
    """
    # --- Auth + permission check ---
    user, error = get_current_user()
    if error:
        return error

    perms = get_user_permissions(user)
    if 'role.manage' not in perms:
        return jsonify({'status': 'error', 'message': 'Permission denied'}), 403

    # --- Look up target role (must belong to same tenant) ---
    role = db.session.get(Role, role_id)
    if role is None or role.tenant_id != user.tenant_id:
        return jsonify({'status': 'error', 'message': 'Role not found'}), 404

    # --- Parse request body ---
    body = request.get_json(silent=True)
    if body is None or not isinstance(body, dict):
        body = {}

    new_parent_id = body.get('parent_role_id')
    new_perm_codes = body.get('permissions')
    if new_perm_codes is not None and not isinstance(new_perm_codes, list):
        return jsonify({'status': 'error', 'message': 'Invalid permissions format'}), 400

    # --- Validate parent_role_id ---
    if new_parent_id is not None:
        parent_role = db.session.get(Role, new_parent_id)
        if parent_role is None:
            return jsonify({'status': 'error', 'message': 'Parent role not found'}), 400
        if parent_role.tenant_id != user.tenant_id:
            return jsonify({'status': 'error', 'message': 'Parent role must belong to the same tenant'}), 400

        # --- Cycle detection: BFS from proposed parent, check if role_id is an ancestor ---
        # Expire the session to ensure we read the latest committed state,
        # avoiding stale identity-map data from prior requests in the same process.
        db.session.expire_all()
        visited = set()
        queue = deque([new_parent_id])
        while queue:
            current_id = queue.popleft()
            if current_id in visited:
                continue
            if current_id == role_id:
                return jsonify({'status': 'error', 'message': 'Inheritance cycle detected'}), 400
            visited.add(current_id)
            current_role = db.session.get(Role, current_id)
            if current_role and current_role.parent_role_id is not None:
                queue.append(current_role.parent_role_id)

    # --- Update parent ---
    role.parent_role_id = new_parent_id

    # --- Update permissions ---
    if new_perm_codes is not None:
        new_perm_objects = []
        if new_perm_codes:
            new_perm_objects = Permission.query.filter(Permission.code.in_(new_perm_codes)).all()
        role.permissions = new_perm_objects

    db.session.commit()

    return jsonify({
        'status': 'ok',
        'data': {
            'id': role.id,
            'name': role.name,
            'parent_role_id': role.parent_role_id,
            'permissions': [p.code for p in role.permissions],
        },
    }), 200


# ------------------------------------------------------------------
# 4. POST /users/<id>/roles — Assign Role to User
# ------------------------------------------------------------------

@role_bp.route('/users/<int:user_id>/roles', methods=['POST'])
def assign_role(user_id):
    """Assign a role to a user.

    Request JSON:
        {"role_id": int}

    Success (200):
        {"status": "ok", "data": {}}

    Errors:
        401 — missing / invalid token
        403 — user lacks role.manage, or cross-tenant assignment
        404 — target user or role not found
        400 — missing role_id in request
    """
    # --- Auth + permission check ---
    user, error = get_current_user()
    if error:
        return error

    perms = get_user_permissions(user)
    if 'role.manage' not in perms:
        return jsonify({'status': 'error', 'message': 'Permission denied'}), 403

    # --- Validate request body ---
    body = request.get_json(silent=True)
    if body is None or not isinstance(body, dict):
        return jsonify({'status': 'error', 'message': 'Invalid request body'}), 400

    role_id = body.get('role_id')
    if role_id is None:
        return jsonify({'status': 'error', 'message': 'Missing role_id'}), 400

    # --- Look up target user ---
    target_user = db.session.get(User, user_id)
    if target_user is None:
        return jsonify({'status': 'error', 'message': 'User not found'}), 404

    # --- Look up role ---
    role = db.session.get(Role, role_id)
    if role is None:
        return jsonify({'status': 'error', 'message': 'Role not found'}), 404

    # --- Cross-tenant guard ---
    if role.tenant_id != target_user.tenant_id:
        return jsonify({'status': 'error', 'message': 'Role and user must belong to the same tenant'}), 403

    # --- Assign role via ORM relationship (idempotent) ---
    if role not in target_user.roles:
        target_user.roles.append(role)
        db.session.commit()

    return jsonify({'status': 'ok', 'data': {}}), 200


# ------------------------------------------------------------------
# 5. DELETE /users/<id>/roles/<role_id> — Remove Role from User
# ------------------------------------------------------------------

@role_bp.route('/users/<int:user_id>/roles/<int:role_id>', methods=['DELETE'])
def remove_role(user_id, role_id):
    """Remove a role from a user (idempotent — no error if not assigned).

    Success (200):
        {"status": "ok", "data": {}}

    Errors:
        401 — missing / invalid token
        403 — user lacks role.manage
        404 — target user not found
    """
    # --- Auth + permission check ---
    user, error = get_current_user()
    if error:
        return error

    perms = get_user_permissions(user)
    if 'role.manage' not in perms:
        return jsonify({'status': 'error', 'message': 'Permission denied'}), 403

    # --- Look up target user ---
    target_user = db.session.get(User, user_id)
    if target_user is None:
        return jsonify({'status': 'error', 'message': 'User not found'}), 404

    # --- Remove role via ORM relationship (idempotent) ---
    role = db.session.get(Role, role_id)
    if role is not None and role in target_user.roles:
        target_user.roles.remove(role)
        db.session.commit()

    return jsonify({'status': 'ok', 'data': {}}), 200
