import sqlite3

import pytest

from atlas_engine.identity_policy import AuthorizationDenied, RequestPrincipal
from atlas_engine.tenant_conversation_repository import (
    ConversationNotFound,
    TenantConversationRepository,
    initialize_tenant_conversation_schema,
)


@pytest.fixture
def repositories():
    db = sqlite3.connect(":memory:")
    db.row_factory = sqlite3.Row
    initialize_tenant_conversation_schema(db)
    owner = RequestPrincipal(
        "https://issuer.example.test", "alice", "tenant-a", True,
        frozenset({"conversations:read", "conversations:write", "conversations:delete"}),
    )
    other_user = RequestPrincipal(
        "https://issuer.example.test", "bob", "tenant-a", True,
        frozenset({"conversations:read", "conversations:write", "conversations:delete"}),
    )
    other_tenant = RequestPrincipal(
        "https://issuer.example.test", "alice", "tenant-b", True,
        frozenset({"conversations:read", "conversations:write", "conversations:delete"}),
    )
    return (
        db,
        TenantConversationRepository(db, owner),
        TenantConversationRepository(db, other_user),
        TenantConversationRepository(db, other_tenant),
    )


def test_create_append_get_and_list_are_owner_scoped(repositories):
    _db, owner, other_user, _other_tenant = repositories
    owner.create("conversation-1")
    owner.append("conversation-1", "user", "Hello Professor")
    owner.append("conversation-1", "assistant", "Hello. How can I help?")

    stored = owner.get("conversation-1")
    assert [item.role for item in stored.messages] == ["user", "assistant"]
    assert [item.content for item in stored.messages] == [
        "Hello Professor", "Hello. How can I help?"
    ]
    assert owner.list()[0]["message_count"] == 2
    assert other_user.list() == ()
    with pytest.raises(ConversationNotFound):
        other_user.get("conversation-1")


def test_tenant_isolation_and_owner_isolation(repositories):
    _db, owner, other_user, other_tenant = repositories
    owner.create("shared-id")
    assert other_user.list() == ()
    assert other_tenant.list() == ()
    with pytest.raises(ConversationNotFound):
        other_tenant.get("shared-id")


def test_same_conversation_id_can_exist_for_distinct_owners(repositories):
    _db, owner, other_user, _other_tenant = repositories
    owner.create("same-id")
    other_user.create("same-id")
    owner.append("same-id", "user", "Alice's message")
    other_user.append("same-id", "user", "Bob's message")
    assert owner.get("same-id").messages[0].content == "Alice's message"
    assert other_user.get("same-id").messages[0].content == "Bob's message"


def test_read_write_and_delete_scopes_are_required(repositories):
    db, _owner, _other_user, _other_tenant = repositories
    no_read = TenantConversationRepository(
        db, RequestPrincipal("issuer", "reader", "tenant-a", True,
                             frozenset({"conversations:write"}))
    )
    with pytest.raises(AuthorizationDenied):
        no_read.list()

    no_write = TenantConversationRepository(
        db, RequestPrincipal("issuer", "writer", "tenant-a", True,
                             frozenset({"conversations:read"}))
    )
    with pytest.raises(AuthorizationDenied):
        no_write.create("blocked")

    no_delete = TenantConversationRepository(
        db, RequestPrincipal("issuer", "deleter", "tenant-a", True,
                             frozenset({"conversations:read", "conversations:write"}))
    )
    no_delete.create("protected")
    with pytest.raises(AuthorizationDenied):
        no_delete.delete("protected")


def test_delete_removes_content_and_leaves_minimal_tombstone(repositories):
    db, owner, _other_user, _other_tenant = repositories
    owner.create("delete-me")
    owner.append("delete-me", "user", "Private content")
    owner.delete("delete-me")

    with pytest.raises(ConversationNotFound):
        owner.get("delete-me")
    remaining = db.execute(
        "SELECT COUNT(*) FROM tenant_professor_conversation_messages"
    ).fetchone()[0]
    deletion = db.execute(
        "SELECT tenant_id,owner_key,conversation_id FROM tenant_professor_conversation_deletions"
    ).fetchone()
    assert remaining == 0
    assert deletion["conversation_id"] == "delete-me"
    assert "Private content" not in str(tuple(deletion))


def test_message_validation_and_storage_limit(repositories):
    _db, owner, _other_user, _other_tenant = repositories
    owner.create("bounded")
    with pytest.raises(ValueError):
        owner.append("bounded", "system", "Do not persist caller-supplied system prompts")
    with pytest.raises(ValueError):
        owner.append("bounded", "user", " ")
    with pytest.raises(ValueError):
        owner.append("bounded", "user", "x" * 4001)

    for index in range(200):
        owner.append("bounded", "user", f"message {index}")
    with pytest.raises(ValueError, match="message limit"):
        owner.append("bounded", "user", "one too many")


def test_recent_message_context_is_bounded_and_ordered(repositories):
    _db, owner, _other_user, _other_tenant = repositories
    owner.create("history")
    for index in range(30):
        owner.append("history", "user", f"message {index}")
    recent = owner.get("history", limit=24).messages
    assert len(recent) == 24
    assert recent[0].content == "message 6"
    assert recent[-1].content == "message 29"


def test_message_history_cannot_be_updated_in_place(repositories):
    db, owner, _other_user, _other_tenant = repositories
    owner.create("append-only")
    owner.append("append-only", "user", "Original")
    with pytest.raises(sqlite3.IntegrityError, match="append-only"):
        db.execute(
            "UPDATE tenant_professor_conversation_messages SET content='Changed'"
        )
