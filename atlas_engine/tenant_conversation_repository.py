"""Tenant-owned persistent conversation storage for Professor.

Conversation content is scoped to a verified tenant principal and a stable
pseudonymous owner key. This repository never calls a reasoning provider or
performs external actions.
"""
from __future__ import annotations

import hashlib
import sqlite3
from dataclasses import dataclass

from .sqlite_transaction import atomic_transaction

from .identity_policy import RequestPrincipal, authorize_tenant_resource

MAX_STORED_MESSAGES = 200
MAX_MESSAGE_CHARS = 4_000
MAX_CONVERSATION_ID_CHARS = 128


class ConversationNotFound(LookupError):
    """The conversation is not owned by the authenticated principal."""


@dataclass(frozen=True)
class StoredConversationMessage:
    ordinal: int
    role: str
    content: str
    created_at: str


@dataclass(frozen=True)
class StoredConversation:
    conversation_id: str
    created_at: str
    updated_at: str
    messages: tuple[StoredConversationMessage, ...]


def initialize_tenant_conversation_schema(db: sqlite3.Connection) -> None:
    db.execute("PRAGMA foreign_keys=ON")
    db.executescript("""
    CREATE TABLE IF NOT EXISTS tenant_professor_conversations (
      tenant_id TEXT NOT NULL,
      owner_key TEXT NOT NULL,
      conversation_id TEXT NOT NULL,
      created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
      updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
      PRIMARY KEY(tenant_id,owner_key,conversation_id)
    );
    CREATE INDEX IF NOT EXISTS idx_professor_conversations_recent
      ON tenant_professor_conversations(tenant_id,owner_key,updated_at DESC);
    CREATE TABLE IF NOT EXISTS tenant_professor_conversation_messages (
      tenant_id TEXT NOT NULL,
      owner_key TEXT NOT NULL,
      conversation_id TEXT NOT NULL,
      ordinal INTEGER NOT NULL CHECK(ordinal>=0),
      role TEXT NOT NULL CHECK(role IN ('user','assistant')),
      content TEXT NOT NULL CHECK(length(content) BETWEEN 1 AND 4000),
      created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
      PRIMARY KEY(tenant_id,owner_key,conversation_id,ordinal),
      FOREIGN KEY(tenant_id,owner_key,conversation_id)
        REFERENCES tenant_professor_conversations(tenant_id,owner_key,conversation_id)
        ON DELETE CASCADE
    );
    CREATE INDEX IF NOT EXISTS idx_professor_conversation_messages_recent
      ON tenant_professor_conversation_messages(tenant_id,owner_key,conversation_id,ordinal DESC);
    CREATE TRIGGER IF NOT EXISTS professor_conversation_messages_no_update
      BEFORE UPDATE ON tenant_professor_conversation_messages BEGIN
      SELECT RAISE(ABORT,'conversation message history is append-only');
    END;
    CREATE TABLE IF NOT EXISTS tenant_professor_conversation_deletions (
      deletion_id INTEGER PRIMARY KEY AUTOINCREMENT,
      tenant_id TEXT NOT NULL,
      owner_key TEXT NOT NULL,
      conversation_id TEXT NOT NULL,
      deleted_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
    );
    CREATE INDEX IF NOT EXISTS idx_professor_conversation_deletions
      ON tenant_professor_conversation_deletions(tenant_id,owner_key,deletion_id);
    CREATE TRIGGER IF NOT EXISTS professor_conversation_deletions_no_update
      BEFORE UPDATE ON tenant_professor_conversation_deletions BEGIN
      SELECT RAISE(ABORT,'conversation deletion history is append-only');
    END;
    CREATE TRIGGER IF NOT EXISTS professor_conversation_deletions_no_delete
      BEFORE DELETE ON tenant_professor_conversation_deletions BEGIN
      SELECT RAISE(ABORT,'conversation deletion history is append-only');
    END;
    """)


class TenantConversationRepository:
    """Tenant- and owner-filtered conversation storage with explicit deletion."""

    def __init__(self, db: sqlite3.Connection, principal: RequestPrincipal):
        if not isinstance(db, sqlite3.Connection):
            raise TypeError("A caller-owned SQLite connection is required.")
        if not isinstance(principal, RequestPrincipal):
            raise TypeError("A verified RequestPrincipal is required.")
        self.db = db
        self.db.execute("PRAGMA foreign_keys=ON")
        self.principal = principal
        self.owner_key = hashlib.sha256(
            (principal.issuer + "\0" + principal.subject).encode("utf-8")
        ).hexdigest()

    def _auth(self, scope: str) -> None:
        authorize_tenant_resource(self.principal, self.principal.tenant_id, {scope})

    @staticmethod
    def _validate_id(conversation_id: str) -> str:
        if (
            not isinstance(conversation_id, str)
            or not conversation_id.strip()
            or len(conversation_id) > MAX_CONVERSATION_ID_CHARS
        ):
            raise ValueError("Conversation ID must be a non-empty bounded string.")
        return conversation_id.strip()

    def create(self, conversation_id: str) -> str:
        self._auth("conversations:write")
        conversation_id = self._validate_id(conversation_id)
        try:
            with atomic_transaction(self.db):
                self.db.execute(
                    """INSERT INTO tenant_professor_conversations
                       (tenant_id,owner_key,conversation_id) VALUES(?,?,?)""",
                    (self.principal.tenant_id, self.owner_key, conversation_id),
                )
        except sqlite3.IntegrityError:
            raise ValueError("Conversation ID already exists for this owner.") from None
        return conversation_id

    def get(self, conversation_id: str, *, limit: int = 24) -> StoredConversation:
        self._auth("conversations:read")
        conversation_id = self._validate_id(conversation_id)
        if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= MAX_STORED_MESSAGES:
            raise ValueError("Message limit must be between 1 and 200.")
        row = self.db.execute(
            """SELECT conversation_id,created_at,updated_at
               FROM tenant_professor_conversations
               WHERE tenant_id=? AND owner_key=? AND conversation_id=?""",
            (self.principal.tenant_id, self.owner_key, conversation_id),
        ).fetchone()
        if row is None:
            raise ConversationNotFound("Conversation was not found.")
        messages = self.db.execute(
            """SELECT ordinal,role,content,created_at
               FROM tenant_professor_conversation_messages
               WHERE tenant_id=? AND owner_key=? AND conversation_id=?
               ORDER BY ordinal DESC LIMIT ?""",
            (self.principal.tenant_id, self.owner_key, conversation_id, limit),
        ).fetchall()
        ordered = tuple(
            StoredConversationMessage(
                ordinal=item["ordinal"],
                role=item["role"],
                content=item["content"],
                created_at=item["created_at"],
            )
            for item in reversed(messages)
        )
        return StoredConversation(
            conversation_id=row["conversation_id"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            messages=ordered,
        )

    def list(self, *, limit: int = 50) -> tuple[dict[str, object], ...]:
        self._auth("conversations:read")
        if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 200:
            raise ValueError("Conversation limit must be between 1 and 200.")
        rows = self.db.execute(
            """SELECT c.conversation_id,c.created_at,c.updated_at,
                      COUNT(m.ordinal) AS message_count
               FROM tenant_professor_conversations c
               LEFT JOIN tenant_professor_conversation_messages m
                 ON m.tenant_id=c.tenant_id AND m.owner_key=c.owner_key
                AND m.conversation_id=c.conversation_id
               WHERE c.tenant_id=? AND c.owner_key=?
               GROUP BY c.tenant_id,c.owner_key,c.conversation_id
               ORDER BY c.updated_at DESC,c.conversation_id LIMIT ?""",
            (self.principal.tenant_id, self.owner_key, limit),
        ).fetchall()
        return tuple(dict(row) for row in rows)

    def append(self, conversation_id: str, role: str, content: str) -> StoredConversationMessage:
        self._auth("conversations:write")
        conversation_id = self._validate_id(conversation_id)
        if role not in {"user", "assistant"}:
            raise ValueError("Only user and assistant messages may be persisted.")
        if not isinstance(content, str) or not content.strip() or len(content) > MAX_MESSAGE_CHARS:
            raise ValueError("Message content must contain 1 to 4000 characters.")
        with atomic_transaction(self.db):

            exists = self.db.execute(
                """SELECT 1 FROM tenant_professor_conversations
                   WHERE tenant_id=? AND owner_key=? AND conversation_id=?""",
                (self.principal.tenant_id, self.owner_key, conversation_id),
            ).fetchone()
            if exists is None:
                raise ConversationNotFound("Conversation was not found.")
            count = self.db.execute(
                """SELECT COUNT(*) AS n FROM tenant_professor_conversation_messages
                   WHERE tenant_id=? AND owner_key=? AND conversation_id=?""",
                (self.principal.tenant_id, self.owner_key, conversation_id),
            ).fetchone()["n"]
            if count >= MAX_STORED_MESSAGES:
                raise ValueError("Conversation has reached its message limit.")
            ordinal = self.db.execute(
                """SELECT COALESCE(MAX(ordinal),-1)+1 AS next_ordinal
                   FROM tenant_professor_conversation_messages
                   WHERE tenant_id=? AND owner_key=? AND conversation_id=?""",
                (self.principal.tenant_id, self.owner_key, conversation_id),
            ).fetchone()["next_ordinal"]
            row = self.db.execute(
                """INSERT INTO tenant_professor_conversation_messages
                   (tenant_id,owner_key,conversation_id,ordinal,role,content)
                   VALUES(?,?,?,?,?,?) RETURNING ordinal,role,content,created_at""",
                (self.principal.tenant_id, self.owner_key, conversation_id, ordinal, role, content.strip()),
            ).fetchone()
            self.db.execute(
                """UPDATE tenant_professor_conversations SET updated_at=CURRENT_TIMESTAMP
                   WHERE tenant_id=? AND owner_key=? AND conversation_id=?""",
                (self.principal.tenant_id, self.owner_key, conversation_id),
            )
        return StoredConversationMessage(row["ordinal"], row["role"], row["content"], row["created_at"])

    def append_turn(
        self,
        conversation_id: str,
        user_content: str,
        assistant_content: str,
        *,
        create_if_missing: bool = False,
    ) -> tuple[StoredConversationMessage, StoredConversationMessage]:
        """Atomically persist one complete user/assistant turn."""
        self._auth("conversations:write")
        conversation_id = self._validate_id(conversation_id)
        for content in (user_content, assistant_content):
            if not isinstance(content, str) or not content.strip() or len(content) > MAX_MESSAGE_CHARS:
                raise ValueError("Message content must contain 1 to 4000 characters.")
        with atomic_transaction(self.db):

            if create_if_missing:
                try:
                    self.db.execute(
                        """INSERT INTO tenant_professor_conversations
                           (tenant_id,owner_key,conversation_id) VALUES(?,?,?)""",
                        (self.principal.tenant_id, self.owner_key, conversation_id),
                    )
                except sqlite3.IntegrityError:
                    raise ValueError("Conversation ID already exists for this owner.") from None
            exists = self.db.execute(
                """SELECT 1 FROM tenant_professor_conversations
                   WHERE tenant_id=? AND owner_key=? AND conversation_id=?""",
                (self.principal.tenant_id, self.owner_key, conversation_id),
            ).fetchone()
            if exists is None:
                raise ConversationNotFound("Conversation was not found.")
            count = self.db.execute(
                """SELECT COUNT(*) AS n FROM tenant_professor_conversation_messages
                   WHERE tenant_id=? AND owner_key=? AND conversation_id=?""",
                (self.principal.tenant_id, self.owner_key, conversation_id),
            ).fetchone()["n"]
            if count + 2 > MAX_STORED_MESSAGES:
                raise ValueError("Conversation has reached its message limit.")
            first_ordinal = count
            stored = []
            for offset, (role, content) in enumerate(
                (("user", user_content), ("assistant", assistant_content))
            ):
                row = self.db.execute(
                    """INSERT INTO tenant_professor_conversation_messages
                       (tenant_id,owner_key,conversation_id,ordinal,role,content)
                       VALUES(?,?,?,?,?,?) RETURNING ordinal,role,content,created_at""",
                    (
                        self.principal.tenant_id, self.owner_key, conversation_id,
                        first_ordinal + offset, role, content.strip(),
                    ),
                ).fetchone()
                stored.append(
                    StoredConversationMessage(
                        row["ordinal"], row["role"], row["content"], row["created_at"]
                    )
                )
            self.db.execute(
                """UPDATE tenant_professor_conversations SET updated_at=CURRENT_TIMESTAMP
                   WHERE tenant_id=? AND owner_key=? AND conversation_id=?""",
                (self.principal.tenant_id, self.owner_key, conversation_id),
            )
        return stored[0], stored[1]

    def delete(self, conversation_id: str) -> None:
        self._auth("conversations:delete")
        conversation_id = self._validate_id(conversation_id)
        with atomic_transaction(self.db):

            cursor = self.db.execute(
                """DELETE FROM tenant_professor_conversations
                   WHERE tenant_id=? AND owner_key=? AND conversation_id=?""",
                (self.principal.tenant_id, self.owner_key, conversation_id),
            )
            if cursor.rowcount != 1:
                raise ConversationNotFound("Conversation was not found.")
            self.db.execute(
                """INSERT INTO tenant_professor_conversation_deletions
                   (tenant_id,owner_key,conversation_id) VALUES(?,?,?)""",
                (self.principal.tenant_id, self.owner_key, conversation_id),
            )
