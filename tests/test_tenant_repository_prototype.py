import sqlite3

import pytest

from atlas_engine.identity_policy import AuthorizationDenied, RequestPrincipal
from atlas_engine.tenant_repository_prototype import (
    TenantTaskNotFound,
    TenantTaskRepository,
    initialize_prototype_schema,
)


def principal(tenant_id, scopes=frozenset({"tasks:read", "tasks:write"}), active=True):
    return RequestPrincipal(
        issuer="https://issuer.example.test/",
        subject=f"user-{tenant_id}",
        tenant_id=tenant_id,
        membership_active=active,
        scopes=scopes,
    )


@pytest.fixture
def connection():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    initialize_prototype_schema(conn)
    yield conn
    conn.close()


def test_tenant_a_cannot_read_or_list_tenant_b_tasks(connection):
    repo_a = TenantTaskRepository(connection, principal("tenant-a"))
    repo_b = TenantTaskRepository(connection, principal("tenant-b"))
    task_b = repo_b.create_task("Company B confidential task")

    assert repo_a.list_tasks() == []
    with pytest.raises(TenantTaskNotFound, match="Task was not found"):
        repo_a.get_task(task_b)


def test_cross_tenant_and_missing_task_have_same_not_found_behavior(connection):
    repo_a = TenantTaskRepository(connection, principal("tenant-a"))
    repo_b = TenantTaskRepository(connection, principal("tenant-b"))
    task_b = repo_b.create_task("Private task")

    with pytest.raises(TenantTaskNotFound) as cross_tenant:
        repo_a.get_task(task_b)
    with pytest.raises(TenantTaskNotFound) as missing:
        repo_a.get_task(999999)
    assert str(cross_tenant.value) == str(missing.value)


def test_tenant_a_cannot_attach_attempt_to_tenant_b_task(connection):
    repo_a = TenantTaskRepository(connection, principal("tenant-a"))
    repo_b = TenantTaskRepository(connection, principal("tenant-b"))
    task_b = repo_b.create_task("Company B task")

    with pytest.raises(TenantTaskNotFound, match="Task was not found"):
        repo_a.create_attempt(task_b, "forged cross-tenant child")
    assert repo_b.list_attempts(task_b) == []


def test_attempts_are_tenant_filtered_and_parent_joined(connection):
    repo_a = TenantTaskRepository(connection, principal("tenant-a"))
    repo_b = TenantTaskRepository(connection, principal("tenant-b"))
    task_a = repo_a.create_task("A task")
    task_b = repo_b.create_task("B task")
    repo_a.create_attempt(task_a, "A outcome")
    repo_b.create_attempt(task_b, "B outcome")

    assert [row["outcome"] for row in repo_a.list_attempts(task_a)] == ["A outcome"]
    assert [row["outcome"] for row in repo_b.list_attempts(task_b)] == ["B outcome"]


def test_tenant_identity_is_taken_from_principal_not_method_arguments(connection):
    repo = TenantTaskRepository(connection, principal("tenant-a"))
    task_id = repo.create_task("Owned by A")
    row = repo.get_task(task_id)
    assert row["tenant_id"] == "tenant-a"


def test_inactive_principal_is_denied_before_read_or_write(connection):
    repo = TenantTaskRepository(connection, principal("tenant-a", active=False))
    with pytest.raises(AuthorizationDenied):
        repo.list_tasks()
    with pytest.raises(AuthorizationDenied):
        repo.create_task("Must not be inserted")


def test_missing_scope_is_denied(connection):
    repo = TenantTaskRepository(connection, principal("tenant-a", scopes=frozenset({"tasks:read"})))
    with pytest.raises(AuthorizationDenied):
        repo.create_task("No write permission")


def test_repository_rejects_forged_dictionary_principal(connection):
    with pytest.raises(AuthorizationDenied):
        TenantTaskRepository(connection, {"tenant_id": "tenant-a", "scopes": ["tasks:read"]})


def test_database_composite_foreign_key_rejects_cross_tenant_child(connection):
    repo_a = TenantTaskRepository(connection, principal("tenant-a"))
    task_a = repo_a.create_task("A parent")
    with pytest.raises(sqlite3.IntegrityError):
        connection.execute(
            """INSERT INTO tenant_task_attempts (tenant_id, task_id, outcome)
               VALUES (?, ?, ?)""",
            ("tenant-b", task_a, "invalid child"),
        )


def test_update_is_limited_to_the_owning_tenant(connection):
    repo_a = TenantTaskRepository(connection, principal("tenant-a"))
    repo_b = TenantTaskRepository(connection, principal("tenant-b"))
    task_b = repo_b.create_task("Original B title")

    with pytest.raises(TenantTaskNotFound):
        repo_a.update_task(task_b, "Attempted takeover")
    assert repo_b.get_task(task_b)["title"] == "Original B title"

    task_a = repo_a.create_task("Original A title")
    assert repo_a.update_task(task_a, "Updated A title")["title"] == "Updated A title"


def test_delete_is_limited_to_the_owning_tenant_and_cascades_children(connection):
    repo_a = TenantTaskRepository(connection, principal("tenant-a"))
    repo_b = TenantTaskRepository(connection, principal("tenant-b"))
    task_b = repo_b.create_task("B protected")
    attempt_b = repo_b.create_attempt(task_b, "B attempt")

    with pytest.raises(TenantTaskNotFound):
        repo_a.delete_task(task_b)
    assert repo_b.get_task(task_b)["title"] == "B protected"
    assert repo_b.list_attempts(task_b)[0]["attempt_id"] == attempt_b

    repo_b.delete_task(task_b)
    with pytest.raises(TenantTaskNotFound):
        repo_b.get_task(task_b)
    assert connection.execute(
        "SELECT COUNT(*) FROM tenant_task_attempts WHERE tenant_id = ? AND task_id = ?",
        ("tenant-b", task_b),
    ).fetchone()[0] == 0


def test_update_and_delete_require_write_scope(connection):
    reader = TenantTaskRepository(
        connection, principal("tenant-a", scopes=frozenset({"tasks:read"}))
    )
    writer = TenantTaskRepository(connection, principal("tenant-a"))
    task_id = writer.create_task("Protected")
    with pytest.raises(AuthorizationDenied):
        reader.update_task(task_id, "No permission")
    with pytest.raises(AuthorizationDenied):
        reader.delete_task(task_id)
    assert writer.get_task(task_id)["title"] == "Protected"
