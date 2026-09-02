from fastapi.testclient import TestClient

from app.main import app


def test_root_describes_the_public_service() -> None:
    response = TestClient(app).get("/")

    assert response.status_code == 200
    assert response.json() == {
        "name": "Youtube2knowledge API",
        "status": "ok",
        "health": "/healthz",
        "app": "https://youtube2knowledge-five.vercel.app/",
    }
