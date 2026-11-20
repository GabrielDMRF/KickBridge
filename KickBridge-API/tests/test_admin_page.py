from fastapi.testclient import TestClient


def test_admin_page_serves_static_html(client: TestClient) -> None:
    response = client.get("/admin")

    assert response.status_code == 200
    assert "Administración del servidor" in response.text
