"""Row-level security helpers shared by migrations and tests.

Model:
- The **migration role** (connection user that runs Alembic) owns every table. Owners bypass RLS
  (we don't FORCE it), so migrations and the seed are unaffected.
- The **app role** (`igs_app` by default) owns nothing and has no BYPASSRLS. Every tenant-scoped
  table has one policy: `tenant_id = current_setting('app.tenant_id')::uuid`, for reads and
  writes. `session_scope()` sets that GUC per transaction.
- With the GUC unset, `current_setting(..., true)` is NULL and the policy matches no rows:
  forgetting the tenant fails closed.

In Cloud SQL the service account's IAM user is granted membership in `igs_app`; locally the
connection user is a superuser, so `session_scope` can `SET LOCAL ROLE igs_app` to exercise the
same policies (see `IGS_DB_APP_ROLE`).
"""

APP_ROLE = "igs_app"
TENANT_GUC = "app.tenant_id"

# Tables without tenant_id: readable by the app role, not row-filtered.
UNSCOPED_TABLES = ("tenants",)

# Append-only: the app role may INSERT and SELECT, never UPDATE or DELETE.
APPEND_ONLY_TABLES = ("audit_log", "messages")


def enable_rls_sql(table: str, app_role: str = APP_ROLE) -> list[str]:
    policy = f"{table}_tenant_isolation"
    predicate = f"tenant_id = NULLIF(current_setting('{TENANT_GUC}', true), '')::uuid"
    dml = "SELECT, INSERT" if table in APPEND_ONLY_TABLES else "SELECT, INSERT, UPDATE, DELETE"
    return [
        f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY",
        f"CREATE POLICY {policy} ON {table} AS PERMISSIVE FOR ALL TO {app_role} "
        f"USING ({predicate}) WITH CHECK ({predicate})",
        f"GRANT {dml} ON {table} TO {app_role}",
    ]


def disable_rls_sql(table: str, app_role: str = APP_ROLE) -> list[str]:
    return [
        f"DROP POLICY IF EXISTS {table}_tenant_isolation ON {table}",
        f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY",
        f"REVOKE ALL ON {table} FROM {app_role}",
    ]
