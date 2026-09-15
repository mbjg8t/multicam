from multicam.api.web.app import app


def test_main_page_renders_from_template():
    client = app.test_client()

    response = client.get("/")

    assert response.status_code == 200
    assert b"Multicam" in response.data
    assert b'<img src="/stream">' in response.data


def test_cameras_page_renders_from_template():
    client = app.test_client()

    response = client.get("/cameras")

    assert response.status_code == 200
    assert b"<h2>Cameras</h2>" in response.data


def test_web_static_assets_are_available():
    client = app.test_client()

    for path in (
        "/static/css/index.css",
        "/static/css/cameras.css",
        "/static/js/cameras.js",
    ):
        response = client.get(path)
        assert response.status_code == 200
        assert response.data
