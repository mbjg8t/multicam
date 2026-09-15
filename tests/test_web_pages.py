from multicam.api.web.app import app


def test_main_page_renders_from_template():
    client = app.test_client()

    response = client.get("/")

    assert response.status_code == 200
    assert b"Multicam" in response.data
    assert b'<img src="/stream">' in response.data
    assert b'id="camera-strip"' in response.data
    assert b'Align to' in response.data


def test_cameras_page_renders_from_template():
    client = app.test_client()

    response = client.get("/cameras")

    assert response.status_code == 200
    assert b"<h2>Cameras</h2>" in response.data


def test_alignment_page_renders_from_template():
    client = app.test_client()

    response = client.get("/alignment")

    assert response.status_code == 200
    assert b"Camera Alignment" in response.data
    assert b'id="reference-stage"' in response.data
    assert b'id="target-stage"' in response.data


def test_alignment_status_api_is_available_without_cameras():
    client = app.test_client()

    response = client.get("/api/alignment")

    assert response.status_code == 200
    data = response.get_json()
    assert "reference_camera_id" in data
    assert "target_camera_id" in data
    assert "cameras" in data


def test_web_static_assets_are_available():
    client = app.test_client()

    for path in (
        "/static/css/index.css",
        "/static/css/cameras.css",
        "/static/js/cameras.js",
        "/static/css/alignment.css",
        "/static/js/alignment.js",
        "/static/js/index.js",
    ):
        response = client.get(path)
        assert response.status_code == 200
        assert response.data
