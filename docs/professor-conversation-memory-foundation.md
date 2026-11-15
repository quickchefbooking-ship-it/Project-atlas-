# Professor conversation memory foundation

**Status: tenant-scoped repository prototype implemented; not yet wired into HTTP routes or deployment.**

## Storage model

`atlas_engine/tenant_conversation_repository.py` provides an isolated SQLite repository that requires a verified `RequestPrincipal` and checks a separate scope for each operation:

- `conversations:read` — list or retrieve the owner's conversations.
- `conversations:write` — create a conversation and append user/assistant messages.
- `conversations:delete` — delete one conversation and its message content.

Rows are scoped by tenant ID and a SHA-256 pseudonymous owner key derived from the verified issuer/subject pair. Raw identity subjects are not copied into the conversation tables. The composite primary/foreign keys prevent messages from being attached to another owner's conversation.

## Retention and limits

- Message content is limited to 4,000 characters.
- A conversation is limited to 200 stored messages.
- Retrieval defaults to the latest 24 messages for bounded reasoning context.
- Message history is append-only; an existing message cannot be edited in place.
- Explicit deletion removes the conversation and its message content, leaving a minimal tombstone containing tenant, pseudonymous owner key, conversation ID and deletion time. The tombstone does not retain message text.
- This is a prototype retention mechanism, not a complete retention schedule, backup-erasure guarantee or legal hold system.

## Security boundary

The repository accepts only a server-created immutable `RequestPrincipal`; it does not authenticate tokens. It does not expose HTTP routes, create principals, call a model, construct system prompts, or execute tools. The caller must ensure assistant messages are written only from a trusted provider response, never from a client-supplied role field.

The schema initializer is explicit and has not been added to the live deployment startup path. No live database was migrated. The existing public conversation endpoint remains fail-closed.

## Validation scope

Unit tests cover tenant and owner separation, per-operation scopes, bounded message sizes and counts, recent-context ordering, append-only messages, content deletion and minimal deletion tombstones. Tests use an in-memory SQLite database.

## Next gate

Before general chat is enabled, add the schema to a reviewed isolated-database migration, authenticated HTTP conversation routes, request rate/size limits, assistant-only server append, retention controls, audit review, backup/restore and deletion tests. Then compose the approved provider with the existing `ConversationService` behind explicit deployment configuration. Do not enable paid inference or deploy without a separate release decision.
