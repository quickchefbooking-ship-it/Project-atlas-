import sqlite3

from fastapi import FastAPI
from fastapi.testclient import TestClient

from atlas_engine.http_identity import require_verified_principal
from atlas_engine.identity_policy import RequestPrincipal
from atlas_engine.professor_memory_api import router
from atlas_engine.tenant_professor_memory import initialize_tenant_memory_schema


SCOPES = frozenset({"memory:propose", "memory:approve", "memory:read", "memory:delete"})


def make_client(tmp_path):
    path = tmp_path / "memory-api.sqlite"
    db = sqlite3.connect(path)
    db.row_factory = sqlite3.Row
    initialize_tenant_memory_schema(db)
    db.close()
    app = FastAPI()
    app.state.tenant_data_path = str(path)
    current = {"principal": RequestPrincipal("issuer", "alice", "tenant-a", True, SCOPES)}
    app.dependency_overrides[require_verified_principal] = lambda: current["principal"]
    app.include_router(router)
    return TestClient(app), current


def test_memory_api_requires_explicit_approval_before_retrieval(tmp_path):
    client, _current = make_client(tmp_path)
    created = client.post("/professor/memory/proposals", json={
        "category": "preference", "title": "Answer style",
        "content": "Prefer concise explanations.", "retention_days": 30,
    })
    assert created.status_code == 201
    proposal_id = created.json()["proposal_id"]
    assert created.json()["status"] == "pending"

    before = client.post("/professor/memory/retrieve", json={"query": "concise explanations"})
    assert before.status_code == 200
    assert before.json()["memories"] == []

    approved = client.post(f"/professor/memory/proposals/{proposal_id}/decision", json={
        "decision": "approved", "rationale": "Explicitly approved by the user.",
    })
    assert approved.status_code == 200
    assert approved.json()["retrieval_enabled"] is True
    after = client.post("/professor/memory/retrieve", json={"query": "concise explanations"})
    assert len(after.json()["memories"]) == 1


def test_memory_api_enforces_scopes_and_owner_isolation(tmp_path):
    client, current = make_client(tmp_path)
    created = client.post("/professor/memory/proposals", json={
        "category": "project", "title": "Atlas", "content": "Keep brain first.",
    })
    proposal_id = created.json()["proposal_id"]
    current["principal"] = RequestPrincipal("issuer", "bob", "tenant-a", True, SCOPES)
    assert client.get("/professor/memory/proposals").json()["proposals"] == []
    assert client.post(f"/professor/memory/proposals/{proposal_id}/decision",
                       json={"decision": "approved"}).status_code == 404


def test_memory_api_rejects_extra_fields_and_bounds_retention(tmp_path):
    client, _current = make_client(tmp_path)
    extra = client.post("/professor/memory/proposals", json={
        "category": "x", "title": "x", "content": "y", "secret": "no",
    })
    assert extra.status_code == 422
    excessive = client.post("/professor/memory/proposals", json={
        "category": "x", "title": "x", "content": "y", "retention_days": 99999,
    })
    assert excessive.status_code == 422


def test_memory_api_delete_removes_content(tmp_path):
    client, _current = make_client(tmp_path)
    created = client.post("/professor/memory/proposals", json={
        "category": "context", "title": "Temporary", "content": "Delete this memory.",
    })
    proposal_id = created.json()["proposal_id"]
    assert client.delete(f"/professor/memory/{proposal_id}").status_code == 204
    assert client.get("/professor/memory/proposals?status=all").json()["proposals"] == []

def test_memory_api_exposes_owner_scoped_expiry_cleanup(tmp_path):
    client, _current = make_client(tmp_path)
    created = client.post("/professor/memory/proposals", json={
        "category": "context", "title": "Expired", "content": "Remove after expiry.",
    })
    proposal_id = created.json()["proposal_id"]
    import sqlite3
    db = sqlite3.connect(tmp_path / "memory-api.sqlite")
    db.execute(
        "UPDATE tenant_professor_memory_proposals SET expires_at=? WHERE proposal_id=?",
        ("2000-01-01T00:00:00+00:00", proposal_id),
    )
    db.commit()
    db.close()
    response = client.post("/professor/memory/cleanup")
    assert response.status_code == 200
    assert response.json()["deleted"] == 1
    assert client.get("/professor/memory/proposals?status=all").json()["proposals"] == []


def test_memory_api_cleanup_rejects_unbounded_limits(tmp_path):
    client, _current = make_client(tmp_path)
    assert client.post("/professor/memory/cleanup?limit=501").status_code == 422


def test_memory_api_supersession_requires_confirmation_and_updates_retrieval(tmp_path):
    client, _current = make_client(tmp_path)
    def create_and_approve(title, content):
        created = client.post("/professor/memory/proposals", json={
            "category": "preference", "title": title, "content": content,
        })
        assert created.status_code == 201
        proposal_id = created.json()["proposal_id"]
        approved = client.post(
            f"/professor/memory/proposals/{proposal_id}/decision",
            json={"decision": "approved", "rationale": "Owner approved."},
        )
        assert approved.status_code == 200
        return proposal_id

    old_id = create_and_approve("Answer style", "Give detailed explanations.")
    new_id = create_and_approve("Answer style", "Give concise explanations.")
    assert len(client.post("/professor/memory/retrieve",
                           json={"query": "explanations"}).json()["memories"]) == 2

    denied = client.post(f"/professor/memory/proposals/{old_id}/supersession", json={
        "replacement_proposal_id": new_id, "confirmed": False,
    })
    assert denied.status_code == 422

    confirmed = client.post(f"/professor/memory/proposals/{old_id}/supersession", json={
        "replacement_proposal_id": new_id, "confirmed": True,
        "rationale": "Owner confirmed the newer preference.",
    })
    assert confirmed.status_code == 200
    assert confirmed.json()["status"] == "superseded"
    memories = client.post("/professor/memory/retrieve",
                           json={"query": "explanations"}).json()["memories"]
    assert [item["proposal_id"] for item in memories] == [new_id]
    history = client.get("/professor/memory/supersessions")
    assert history.status_code == 200
    assert history.json()["supersessions"][0]["prior_proposal_id"] == old_id


def test_memory_api_supersession_is_owner_scoped_and_strictly_typed(tmp_path):
    client, current = make_client(tmp_path)
    old = client.post("/professor/memory/proposals", json={
        "category": "preference", "title": "Style", "content": "Old style.",
    }).json()["proposal_id"]
    new = client.post("/professor/memory/proposals", json={
        "category": "preference", "title": "Style", "content": "New style.",
    }).json()["proposal_id"]
    for proposal_id in (old, new):
        assert client.post(f"/professor/memory/proposals/{proposal_id}/decision",
                           json={"decision": "approved"}).status_code == 200

    invalid = client.post(f"/professor/memory/proposals/{old}/supersession", json={
        "replacement_proposal_id": new, "confirmed": 1,
    })
    assert invalid.status_code == 422

    current["principal"] = RequestPrincipal("issuer", "bob", "tenant-a", True, SCOPES)
    assert client.post(f"/professor/memory/proposals/{old}/supersession", json={
        "replacement_proposal_id": new, "confirmed": True,
    }).status_code == 404
    assert client.get("/professor/memory/supersessions").json()["supersessions"] == []
