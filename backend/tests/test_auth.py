from conftest import auth


def _signup(client, email: str = "x@test.dev", password: str = "password123", name: str = "Tester"):
    return client.post(
        "/auth/signup",
        json={"email": email, "password": password, "name": name},
    )


def test_health(client):
    body = client.get("/health").json()
    assert body["status"] == "healthy"


def test_root(client):
    body = client.get("/").json()
    assert body["version"]


def test_signup_creates_free_user(client):
    response = _signup(client, email="alpha@test.dev")
    assert response.status_code == 201
    data = response.json()
    assert data["access_token"]
    assert data["user"]["email"] == "alpha@test.dev"
    assert data["user"]["plan"] == "FREE"
    assert data["user"]["is_demo"] is False


def test_duplicate_email_rejected(client):
    assert _signup(client, email="dup@test.dev").status_code == 201
    assert _signup(client, email="dup@test.dev").status_code == 409


def test_login_and_me(client):
    _signup(client, email="beta@test.dev")
    bad = client.post("/auth/login", json={"email": "beta@test.dev", "password": "wrongpass1"})
    assert bad.status_code == 401

    good = client.post("/auth/login", json={"email": "beta@test.dev", "password": "password123"})
    assert good.status_code == 200
    token = good.json()["access_token"]

    me = client.get("/auth/me", headers=auth(token))
    assert me.status_code == 200
    assert me.json()["email"] == "beta@test.dev"


def test_protected_route_requires_auth(client):
    assert client.get("/auth/me").status_code == 401
    assert client.get("/dashboard/stats").status_code == 401


def test_demo_login(client):
    response = client.post("/auth/demo")
    assert response.status_code == 200
    data = response.json()
    assert data["user"]["is_demo"] is True
    assert data["user"]["plan"] == "PRO"

    token = data["access_token"]
    me = client.get("/auth/me", headers=auth(token))
    assert me.status_code == 200
    assert me.json()["is_demo"] is True