from contextlib import asynccontextmanager

import pytest

pytest.importorskip("jwt")
pytest.importorskip("pwdlib")

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.db import Base, get_db
from app.core.security import create_token
from app.main import app
from app.models import ActionRequest, Document, Organization, User


@pytest.fixture
def tenant_client(monkeypatch):
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    TestingSession = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    db = TestingSession()
    org_a = Organization(id="org-a", name="A")
    org_b = Organization(id="org-b", name="B")
    user_a = User(id="user-a", organization_id="org-a", email="a@example.test",
                  password_hash="unused", role="member")
    user_b = User(id="user-b", organization_id="org-b", email="b@example.test",
                  password_hash="unused", role="admin")
    admin_a = User(id="admin-a", organization_id="org-a", email="admin-a@example.test",
                   password_hash="unused", role="admin")
    db.add_all([org_a, org_b, user_a, user_b, admin_a])
    db.add_all([
        Document(id="doc-a", organization_id="org-a", family_id="family-a", uploaded_by="user-a",
                 filename="a.txt", content_hash="a" * 64, storage_path="a.txt", status="ready"),
        Document(id="doc-b", organization_id="org-b", family_id="family-b", uploaded_by="user-b",
                 filename="b.txt", content_hash="b" * 64, storage_path="b.txt", status="ready"),
        Document(id="doc-c", organization_id="org-a", family_id="family-c", uploaded_by="admin-a",
                 filename="restricted.txt", content_hash="c" * 64, storage_path="c.txt",
                 status="ready", allowed_roles=["engineer"]),
        ActionRequest(id="action-a", organization_id="org-a", requested_by="user-a",
                      kind="report", payload={"summary": "A"}, status="pending_approval"),
        ActionRequest(id="action-b", organization_id="org-b", requested_by="user-b",
                      kind="report", payload={"summary": "B"}, status="pending_approval"),
    ])
    db.commit()

    def override_db():
        yield db

    app.dependency_overrides[get_db] = override_db

    @asynccontextmanager
    async def no_startup(_app):
        yield

    monkeypatch.setattr(app.router, "lifespan_context", no_startup)
    with TestClient(app) as client:
        yield client, create_token(user_a), user_a, create_token(admin_a)
    app.dependency_overrides.clear()
    db.close()
    Base.metadata.drop_all(engine)
    engine.dispose()


def test_document_and_action_lists_are_tenant_scoped(tenant_client):
    client, token, *_ = tenant_client
    headers = {"Authorization": f"Bearer {token}"}

    docs = client.get("/api/documents", headers=headers)
    actions = client.get("/api/actions", headers=headers)

    assert docs.status_code == 200
    assert [row["id"] for row in docs.json()] == ["doc-a"]
    assert actions.status_code == 200
    assert [row["id"] for row in actions.json()] == ["action-a"]


def test_cross_tenant_action_identifier_is_not_disclosed(tenant_client):
    client, _member_token, _, admin_token = tenant_client
    response = client.post("/api/actions/action-b/approve",
                           headers={"Authorization": f"Bearer {admin_token}"})
    assert response.status_code == 404


def test_query_ignores_client_supplied_organization(tenant_client, monkeypatch):
    import app.main as main

    client, token, *_ = tenant_client
    seen = {}

    def fake_search(_db, org_id, _question, **kwargs):
        seen["org_id"] = org_id
        seen["roles"] = kwargs.get("roles")
        seen["user_id"] = kwargs.get("user_id")
        return []

    async def fake_answer(_question, evidence, _history):
        return {"answer": "No evidence", "citations": [], "grounded": False}

    monkeypatch.setattr(main, "search", fake_search)
    monkeypatch.setattr(main, "answer", fake_answer)
    response = client.post("/api/query", headers={"Authorization": f"Bearer {token}"},
                          json={"question": "Which failures occurred?", "organization_id": "org-b"})

    assert response.status_code == 200
    assert seen["org_id"] == "org-a"
    assert seen["roles"] == ("member",)
    assert seen["user_id"] == "user-a"


def test_cross_role_document_is_hidden_from_document_list(tenant_client):
    client, token, *_ = tenant_client
    response = client.get("/api/documents?include_history=true",
                          headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 200
    assert {row["id"] for row in response.json()} == {"doc-a"}


def test_token_cannot_claim_a_different_database_organization(tenant_client):
    import jwt
    from app.core.config import settings

    client, _token, _user, _admin_token = tenant_client
    forged = jwt.encode({"sub": "user-a", "org": "org-b", "role": "admin"},
                        settings.jwt_secret, algorithm="HS256")
    response = client.get("/api/me", headers={"Authorization": f"Bearer {forged}"})
    assert response.status_code == 401
