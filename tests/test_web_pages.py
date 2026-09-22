from multicam.api.web.app import app, startup_urls


def test_main_page_renders_from_template():
    client = app.test_client()

    response = client.get("/")

    assert response.status_code == 200
    assert b"Multicam" in response.data
    assert b'<img src="/stream">' in response.data
    assert b'id="camera-strip"' in response.data
    assert b'Align to' in response.data
    assert b'id="open-focus"' in response.data
    assert b'id="open-dsp"' in response.data


def test_cameras_page_renders_from_template():
    client = app.test_client()

    response = client.get("/cameras")

    assert response.status_code == 200
    assert b"<h2>Cameras</h2>" in response.data
    assert b'id="hardwarePortSelector"' in response.data
    assert b"CAM/DISP0" in response.data
    assert b"CAM/DISP1" in response.data
    assert b"Review Selected Overlays" in response.data


def test_alignment_page_renders_from_template():
    client = app.test_client()

    response = client.get("/alignment")

    assert response.status_code == 200
    assert b"Camera Alignment" in response.data
    assert b'id="reference-stage"' in response.data
    assert b'id="target-stage"' in response.data
    assert b'id="nudge-step"' in response.data
    assert b'id="alignment-model"' in response.data
    assert b'id="clear-points"' in response.data
    assert b'id="fit-quality"' in response.data
    assert b"Guided auto" in response.data
    assert b"Planar precision" in response.data
    assert b'id="download-diagnostics"' in response.data
    assert b'id="selection-zoom"' in response.data
    assert b'id="reset-zoom"' in response.data
    assert b'Auto-find after 2 anchors' in response.data
    assert b'id="auto-match" type="checkbox" disabled' in response.data
    assert 'homography, 6–12 pairs'.encode() in response.data


def test_focus_page_renders_from_template():
    client = app.test_client()

    response = client.get("/focus")

    assert response.status_code == 200
    assert b"Focus sharpness proxy" in response.data
    assert b'id="focus-camera"' in response.data
    assert b'id="roi-preview"' in response.data


def test_dsp_page_renders_from_template():
    client = app.test_client()

    response = client.get("/dsp")

    assert response.status_code == 200
    assert b"DSP Workbench" in response.data
    assert b'id="raw-preview"' in response.data
    assert b'id="processed-preview"' in response.data
    assert b'id="black-percentile"' in response.data
    assert b'id="max-fps"' in response.data
    assert b'id="levels-mode"' in response.data
    assert b'id="denoise-mode"' in response.data
    assert b'id="sharpen-mode"' in response.data
    assert b'id="edge-mode"' in response.data
    assert "Fast 3×3 edges".encode() in response.data
    assert b"Laplacian edges" in response.data
    assert b"Selected camera" in response.data


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
        "/static/css/focus.css",
        "/static/js/focus.js",
        "/static/css/dsp.css",
        "/static/js/dsp.js",
    ):
        response = client.get(path)
        assert response.status_code == 200
        assert response.data


def test_dsp_api_is_available_without_cameras():
    client = app.test_client()

    response = client.get("/api/dsp")

    assert response.status_code == 200
    assert response.get_json()["cameras"] == []


def test_camera_settings_script_includes_preview_resolution_control():
    client = app.test_client()

    response = client.get("/static/js/cameras.js")

    assert response.status_code == 200
    assert b"preview_resolution" in response.data


def test_camera_hardware_selector_is_stable_and_auto_plans():
    client = app.test_client()
    response = client.get("/static/js/cameras.js")

    assert response.status_code == 200
    assert b"hardwarePortStructureKey" in response.data
    assert b"planHardwareConfiguration();" in response.data
    assert b"Apply (Setup Required)" in response.data


def test_startup_urls_include_local_and_lan_addresses():
    assert startup_urls(
        "0.0.0.0",
        5000,
        ["192.168.1.42", "10.0.0.8"],
    ) == [
        "http://localhost:5000",
        "http://192.168.1.42:5000",
        "http://10.0.0.8:5000",
    ]
    assert startup_urls("127.0.0.1", 5050) == [
        "http://localhost:5050"
    ]


def test_alignment_script_includes_auto_match_workflow():
    client = app.test_client()

    response = client.get("/static/js/alignment.js")

    assert response.status_code == 200
    assert b"/api/alignment/auto-point" in response.data
    assert b"/api/alignment/point-pairs" in response.data
    assert b"rms_error_px" in response.data
    assert b"installPanHandler" in response.data
    assert b"zoomViewportAt" in response.data
    assert b"modelSelect.addEventListener('change', refitSelectedModel)" in response.data
    assert b"modelSelect.addEventListener('change', clearMatchPoints)" not in response.data
    assert b"model outlier" in response.data
    assert b"last valid preview remains displayed" in response.data
    assert b"Undo becomes available after an alignment is accepted" in response.data
