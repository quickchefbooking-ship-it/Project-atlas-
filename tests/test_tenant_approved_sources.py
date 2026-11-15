import hashlib
import sqlite3

import pytest

from atlas_engine.tenant_approved_sources import (
    get_approved_tenant_source_document,
    initialize_tenant_approved_source_schema,
    review_tenant_source_document,
    stage_tenant_source_document,
)


def _db(path):
    db = sqlite3.connect(path)
    db.row_factory = sqlite3.Row
    initialize_tenant_approved_source_schema(db)
    return db


def _stage(db, tenant="tenant-a"):
    return stage_tenant_source_document(
        db,
        tenant_id=tenant,
        staged_by="reviewer:stager",
        title="Research source",
        uri="https://example.org/research",
        content="<html><body><p>Verified excerpt.</p></body></html>",
        content_type="text/html",
        metadata={"publisher": "Example Institute"},
    )


def test_tenant_source_is_pending_until_verified_reviewer_approves(tmp_path):
    db = _db(tmp_path / "tenant.sqlite")
    try:
        staged = _stage(db)
        assert staged["state"] == "pending"
        assert get_approved_tenant_source_document(
            db, tenant_id="tenant-a", document_id=staged["document_id"]
        ) is None

        reviewed = review_tenant_source_document(
            db, tenant_id="tenant-a", document_id=staged["document_id"],
            reviewer_id="reviewer:verified-principal", decision="approved",
        )
        db.commit()
        assert reviewed["state"] == "approved"
        assert reviewed["reviewed_by"] == "reviewer:verified-principal"
        source = get_approved_tenant_source_document(
            db, tenant_id="tenant-a", document_id=staged["document_id"]
        )
        assert source["content"] == "<html><body><p>Verified excerpt.</p></body></html>"
        assert source["content_sha256"] == hashlib.sha256(
            source["content"].encode("utf-8")
        ).hexdigest()
    finally:
        db.close()


def test_source_document_id_cannot_cross_tenant_boundary(tmp_path):
    db = _db(tmp_path / "tenant.sqlite")
    try:
        staged = _stage(db, "tenant-a")
        review_tenant_source_document(
            db, tenant_id="tenant-a", document_id=staged["document_id"],
            reviewer_id="reviewer:verified-principal", decision="approved",
        )
        db.commit()
        assert get_approved_tenant_source_document(
            db, tenant_id="tenant-b", document_id=staged["document_id"]
        ) is None
    finally:
        db.close()


def test_source_review_cannot_be_spoofed_or_repeated(tmp_path):
    db = _db(tmp_path / "tenant.sqlite")
    try:
        staged = _stage(db)
        with pytest.raises(ValueError, match="server-derived"):
            review_tenant_source_document(
                db, tenant_id="tenant-a", document_id=staged["document_id"],
                reviewer_id="forged", decision="approved",
            )
        review_tenant_source_document(
            db, tenant_id="tenant-a", document_id=staged["document_id"],
            reviewer_id="reviewer:verified-principal", decision="approved",
        )
        with pytest.raises(ValueError, match="not found"):
            review_tenant_source_document(
                db, tenant_id="tenant-a", document_id=staged["document_id"],
                reviewer_id="reviewer:verified-principal", decision="approved",
            )
    finally:
        db.close()


@pytest.mark.parametrize("uri", [
    "http://example.org/source",
    "https://user:password@example.org/source",
    "https://example.org:8443/source",
    "https://example.org/source#fragment",
])
def test_unsafe_source_uris_are_rejected(tmp_path, uri):
    db = _db(tmp_path / "tenant.sqlite")
    try:
        with pytest.raises(ValueError, match="absolute HTTPS"):
            stage_tenant_source_document(
                db, tenant_id="tenant-a", staged_by="reviewer:stager",
                title="Unsafe", uri=uri, content="Source text",
            )
    finally:
        db.close()


def test_source_snapshot_is_immutable_and_cannot_be_deleted(tmp_path):
    db = _db(tmp_path / "tenant.sqlite")
    try:
        staged = _stage(db)
        with pytest.raises(sqlite3.IntegrityError, match="snapshot is immutable"):
            db.execute(
                "UPDATE tenant_approved_source_documents SET content='forged' "
                "WHERE tenant_id='tenant-a' AND document_id=?",
                (staged["document_id"],),
            )
        db.rollback()
        with pytest.raises(sqlite3.IntegrityError, match="cannot be deleted"):
            db.execute(
                "DELETE FROM tenant_approved_source_documents "
                "WHERE tenant_id='tenant-a' AND document_id=?",
                (staged["document_id"],),
            )
        db.rollback()
    finally:
        db.close()


def test_rejected_source_never_resolves_as_approved(tmp_path):
    db = _db(tmp_path / "tenant.sqlite")
    try:
        staged = _stage(db)
        review_tenant_source_document(
            db, tenant_id="tenant-a", document_id=staged["document_id"],
            reviewer_id="reviewer:verified-principal", decision="rejected",
        )
        db.commit()
        assert get_approved_tenant_source_document(
            db, tenant_id="tenant-a", document_id=staged["document_id"]
        ) is None
    finally:
        db.close()
