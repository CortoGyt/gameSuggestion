def test_health_ok(client):
    response = client.get("/api/v1/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "database": "ok"}


def test_list_games_returns_all(client):
    data = client.get("/api/v1/games").json()
    assert data["total"] == 3
    assert len(data["items"]) == 3


def test_games_have_labels_and_styles(client):
    data = client.get("/api/v1/games?q=Hades").json()
    game = data["items"][0]
    assert game["difficulty"] == "Avancé"
    assert game["randomness"] == "Bas"
    assert game["styles"] == ["Platformer", "Roguelike"]


def test_search_by_name(client):
    data = client.get("/api/v1/games?q=cel").json()
    assert data["total"] == 1
    assert data["items"][0]["name"] == "Celeste"


def test_filter_by_style(client):
    data = client.get("/api/v1/games?style=Platformer").json()
    assert data["total"] == 2


def test_pagination(client):
    data = client.get("/api/v1/games?limit=2&offset=2").json()
    assert data["total"] == 3
    assert len(data["items"]) == 1


def test_limit_too_high_is_rejected(client):
    assert client.get("/api/v1/games?limit=500").status_code == 422


def test_negative_offset_is_rejected(client):
    assert client.get("/api/v1/games?offset=-1").status_code == 422


def test_get_game_by_id(client):
    response = client.get("/api/v1/games/1")
    assert response.status_code == 200
    assert response.json()["name"] == "Celeste"


def test_unknown_game_returns_404(client):
    assert client.get("/api/v1/games/99999").status_code == 404


def test_sql_injection_attempt_is_harmless(client):
    data = client.get("/api/v1/games", params={"q": "' OR 1=1 --"}).json()
    assert data["total"] == 0


def test_cors_allows_streamlit_origin_only(client):
    headers = {"Origin": "http://localhost:8501", "Access-Control-Request-Method": "GET"}
    allowed = client.options("/api/v1/games", headers=headers)
    assert allowed.headers.get("access-control-allow-origin") == "http://localhost:8501"

    headers["Origin"] = "http://evil.example"
    refused = client.options("/api/v1/games", headers=headers)
    assert "access-control-allow-origin" not in refused.headers
