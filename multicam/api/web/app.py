from __future__ import annotations

import io
import time

from flask import Flask, Response, jsonify, request
from PIL import Image

from multicam.backends.aravis import AravisBackend
from multicam.backends.picamera2 import Picamera2Backend
from multicam.core.cameras import CameraManager, FrameBroker
from multicam.core.services import LiveViewService
from multicam.core.state import OverlayLayer, ViewStateStore


app = Flask(__name__)

manager = CameraManager()
manager.register_backend(Picamera2Backend())
manager.register_backend(AravisBackend())

broker = FrameBroker()
state = ViewStateStore()

service = LiveViewService(
    manager=manager,
    broker=broker,
    state=state,
)


def initialize():
    cameras = manager.discover()

    if not cameras:
        raise RuntimeError("No cameras discovered")

    for info in cameras:
        device = manager.open(info.id)
        broker.add_camera(device)

    # Temporary startup defaults only.
    # These will later come from persistent configuration.
    picam = next(
        (c for c in cameras if c.backend == "picamera2"),
        None,
    )

    swir = next(
        (c for c in cameras if c.backend == "aravis"),
        None,
    )

    if picam is not None:
        state.set_base(picam.id)
    else:
        state.set_base(cameras[0].id)

    if swir is not None:
        state.add_overlay(
            OverlayLayer(
                camera_id=swir.id,
                opacity=0.50,
                z_order=0,
            )
        )

    broker.start_all()


def serialize_state():
    current = state.get()

    return {
        "base_camera_id": current.base_camera_id,
        "overlays": [
            {
                "camera_id": layer.camera_id,
                "enabled": layer.enabled,
                "opacity": layer.opacity,
                "display_mode": layer.display_mode,
                "z_order": layer.z_order,
                "transform": {
                    "x": layer.transform.x,
                    "y": layer.transform.y,
                    "scale_x": layer.transform.scale_x,
                    "scale_y": layer.transform.scale_y,
                    "rotation_deg": layer.transform.rotation_deg,
                },
            }
            for layer in current.overlays
        ],
    }


@app.route("/")
def index():
    return """
<!doctype html>
<html>
<head>
    <title>Multicam</title>

    <style>
        html, body {
            margin: 0;
            background: #111;
            color: white;
            font-family: Arial, sans-serif;
        }

        .container {
            display: flex;
            flex-direction: column;
            height: 100vh;
        }

        .header {
            height: 52px;
            box-sizing: border-box;
            padding: 8px 12px;
            background: #222;
            display: flex;
            align-items: center;
            gap: 10px;
        }

        .title {
            font-weight: bold;
            margin-right: 20px;
        }

        button {
            background: #444;
            color: white;
            border: 1px solid #666;
            border-radius: 4px;
            padding: 7px 14px;
            cursor: pointer;
        }

        button:hover {
            background: #555;
        }

        .viewer {
            flex: 1;
            display: flex;
            align-items: center;
            justify-content: center;
            overflow: hidden;
            padding: 10px;
            box-sizing: border-box;
        }

        .viewer img {
            max-width: 100%;
            max-height: 100%;
            object-fit: contain;
        }
    </style>
</head>

<body>
    <div class="container">

        <div class="header">
            <div class="title">Multicam 1.0</div>

            <button onclick="window.open('/cameras', 'multicam-cameras')">
                Cameras
            </button>

            <button disabled>
                Alignment
            </button>

            <button disabled>
                MTF
            </button>
        </div>

        <div class="viewer">
            <img src="/stream">
        </div>

    </div>
</body>
</html>
"""


@app.route("/cameras")
def cameras_page():
    return """
<!doctype html>
<html>
<head>
    <title>Multicam - Cameras</title>

    <style>
        body {
            margin: 0;
            padding: 20px;
            background: #181818;
            color: #eee;
            font-family: Arial, sans-serif;
        }

        h2 {
            margin-top: 0;
        }

        .section {
            background: #242424;
            border: 1px solid #444;
            border-radius: 6px;
            padding: 16px;
            margin-bottom: 18px;
        }

        .camera-info {
            font-size: 13px;
            color: #aaa;
            margin-top: 6px;
        }

        select,
        input[type="range"] {
            margin-top: 8px;
        }

        select {
            background: #333;
            color: white;
            border: 1px solid #666;
            padding: 7px;
            min-width: 350px;
        }

        button {
            background: #444;
            color: white;
            border: 1px solid #666;
            border-radius: 4px;
            padding: 7px 12px;
            cursor: pointer;
        }

        button:hover {
            background: #555;
        }

        .overlay {
            border-top: 1px solid #444;
            padding: 14px 0;
        }

        .overlay:first-child {
            border-top: none;
        }

        .row {
            display: flex;
            align-items: center;
            gap: 12px;
            margin: 8px 0;
        }

        .opacity {
            width: 260px;
        }

        .value {
            width: 45px;
        }

        .remove {
            margin-left: auto;
        }

        .status {
            color: #8f8;
            font-size: 13px;
            min-height: 18px;
        }
    </style>
</head>

<body>

<h2>Cameras</h2>

<div class="section">
    <strong>Base Camera</strong>

    <div>
        <select id="baseCamera"></select>
    </div>

    <div id="baseInfo" class="camera-info"></div>
</div>


<div class="section">
    <strong>Overlays</strong>

    <div id="overlayList"></div>

    <div style="margin-top: 12px;">
        <button onclick="addOverlay()">
            + Add Overlay
        </button>
    </div>
</div>

<div id="status" class="status"></div>


<script>

let cameras = [];
let viewState = null;


async function api(url, options = {}) {
    const response = await fetch(url, options);

    if (!response.ok) {
        const text = await response.text();
        throw new Error(text || response.statusText);
    }

    return response.json();
}


async function refresh() {
    cameras = await api('/api/cameras');
    viewState = await api('/api/state');

    renderBase();
    renderOverlays();
}


function cameraById(id) {
    return cameras.find(c => c.id === id);
}


function cameraLabel(camera) {
    if (!camera) {
        return 'Unknown camera';
    }

    return `${camera.name} [${camera.backend}]`;
}


function renderBase() {
    const select = document.getElementById('baseCamera');

    select.innerHTML = '';

    for (const camera of cameras) {
        const option = document.createElement('option');

        option.value = camera.id;
        option.textContent = cameraLabel(camera);

        if (camera.id === viewState.base_camera_id) {
            option.selected = true;
        }

        select.appendChild(option);
    }

    select.onchange = async () => {
        await api('/api/view/base', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                camera_id: select.value
            })
        });

        await refresh();

        showStatus('Base camera changed');
    };

    const camera = cameraById(viewState.base_camera_id);

    document.getElementById('baseInfo').textContent =
        camera
            ? `${camera.vendor || ''} ${camera.model || ''}`
            : '';
}


function renderOverlays() {
    const container = document.getElementById('overlayList');

    container.innerHTML = '';

    if (viewState.overlays.length === 0) {
        container.innerHTML =
            '<div class="camera-info">No overlays</div>';

        return;
    }

    viewState.overlays.forEach((layer, index) => {

        const camera = cameraById(layer.camera_id);

        const div = document.createElement('div');
        div.className = 'overlay';

        div.innerHTML = `
            <div>
                <strong>${cameraLabel(camera)}</strong>
            </div>

            <div class="row">

                <label>
                    <input
                        type="checkbox"
                        ${layer.enabled ? 'checked' : ''}
                        onchange="setEnabled(
                            '${escapeJs(layer.camera_id)}',
                            this.checked
                        )"
                    >
                    Enabled
                </label>

                <span>Opacity</span>

                <input
                    class="opacity"
                    type="range"
                    min="0"
                    max="1"
                    step="0.01"
                    value="${layer.opacity}"
                    oninput="
                        this.nextElementSibling.textContent =
                        Math.round(this.value * 100) + '%'
                    "
                    onchange="setOpacity(
                        '${escapeJs(layer.camera_id)}',
                        this.value
                    )"
                >

                <span class="value">
                    ${Math.round(layer.opacity * 100)}%
                </span>

                <button
                    class="remove"
                    onclick="removeOverlay(
                        '${escapeJs(layer.camera_id)}'
                    )"
                >
                    Remove
                </button>

            </div>
        `;

        container.appendChild(div);
    });
}


function escapeJs(value) {
    return value
        .replace(/\\\\/g, '\\\\\\\\')
        .replace(/'/g, "\\\\'");
}


async function addOverlay() {
    const used = new Set(
        viewState.overlays.map(o => o.camera_id)
    );

    const camera = cameras.find(
        c =>
            c.id !== viewState.base_camera_id &&
            !used.has(c.id)
    );

    if (!camera) {
        alert('No unused camera is available for another overlay.');
        return;
    }

    await api('/api/overlays', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json'
        },
        body: JSON.stringify({
            camera_id: camera.id,
            opacity: 0.5
        })
    });

    await refresh();

    showStatus('Overlay added');
}


async function removeOverlay(cameraId) {
    await api(
        '/api/overlays/' + encodeURIComponent(cameraId),
        {
            method: 'DELETE'
        }
    );

    await refresh();

    showStatus('Overlay removed');
}


async function setOpacity(cameraId, value) {
    await api(
        '/api/overlays/' + encodeURIComponent(cameraId),
        {
            method: 'PATCH',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                opacity: Number(value)
            })
        }
    );

    viewState = await api('/api/state');

    showStatus('Opacity updated');
}


async function setEnabled(cameraId, enabled) {
    await api(
        '/api/overlays/' + encodeURIComponent(cameraId),
        {
            method: 'PATCH',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                enabled: enabled
            })
        }
    );

    viewState = await api('/api/state');

    showStatus(enabled ? 'Overlay enabled' : 'Overlay disabled');
}


function showStatus(message) {
    const status = document.getElementById('status');

    status.textContent = message;

    setTimeout(() => {
        status.textContent = '';
    }, 1500);
}


refresh().catch(error => {
    console.error(error);
    alert(error);
});

</script>

</body>
</html>
"""


@app.route("/api/cameras")
def cameras_api():
    return jsonify([
        {
            "id": c.id,
            "backend": c.backend,
            "name": c.name,
            "model": c.model,
            "vendor": c.vendor,
            "serial": c.serial,
            "connected": c.connected,
        }
        for c in manager.list_cameras()
    ])


@app.route("/api/state")
def state_api():
    return jsonify(serialize_state())


@app.route("/api/view/base", methods=["POST"])
def set_base_api():
    data = request.get_json(force=True)

    camera_id = data.get("camera_id")

    known_ids = {
        camera.id
        for camera in manager.list_cameras()
    }

    if camera_id not in known_ids:
        return jsonify({
            "error": "Unknown camera"
        }), 404

    state.set_base(camera_id)

    # A camera cannot simultaneously be its own overlay.
    state.remove_overlay(camera_id)

    return jsonify(serialize_state())


@app.route("/api/overlays", methods=["POST"])
def add_overlay_api():
    data = request.get_json(force=True)

    camera_id = data.get("camera_id")
    opacity = float(data.get("opacity", 0.5))

    known_ids = {
        camera.id
        for camera in manager.list_cameras()
    }

    if camera_id not in known_ids:
        return jsonify({
            "error": "Unknown camera"
        }), 404

    current = state.get()

    if camera_id == current.base_camera_id:
        return jsonify({
            "error": "Base camera cannot also be an overlay"
        }), 400

    if any(
        layer.camera_id == camera_id
        for layer in current.overlays
    ):
        return jsonify({
            "error": "Camera is already an overlay"
        }), 400

    state.add_overlay(
        OverlayLayer(
            camera_id=camera_id,
            opacity=max(0.0, min(1.0, opacity)),
            z_order=len(current.overlays),
        )
    )

    return jsonify(serialize_state())


@app.route(
    "/api/overlays/<path:camera_id>",
    methods=["PATCH"],
)
def update_overlay_api(camera_id):
    data = request.get_json(force=True)

    try:
        state.update_overlay(
            camera_id,
            enabled=data.get("enabled"),
            opacity=data.get("opacity"),
        )
    except KeyError:
        return jsonify({
            "error": "Overlay not found"
        }), 404

    return jsonify(serialize_state())


@app.route(
    "/api/overlays/<path:camera_id>",
    methods=["DELETE"],
)
def remove_overlay_api(camera_id):
    state.remove_overlay(camera_id)

    return jsonify(serialize_state())


@app.route("/stream")
def stream():
    def generate():
        while True:
            image = service.get_composite()

            if image is None:
                time.sleep(0.05)
                continue

            buffer = io.BytesIO()

            Image.fromarray(image).save(
                buffer,
                format="JPEG",
                quality=85,
            )

            jpg = buffer.getvalue()

            yield (
                b"--frame\r\n"
                b"Content-Type: image/jpeg\r\n\r\n"
                + jpg
                + b"\r\n"
            )

            time.sleep(0.03)

    return Response(
        generate(),
        mimetype=(
            "multipart/x-mixed-replace;"
            " boundary=frame"
        ),
    )


@app.route("/api/streams")
def streams_api():
    result = []

    for camera in manager.list_cameras():
        stream_state = broker.get_state(camera.id)
        frame = broker.get_latest(camera.id)

        item = {
            "id": camera.id,
            "backend": camera.backend,
            "name": camera.name,
            "running": stream_state.running,
            "frame_count": stream_state.frame_count,
            "last_error": stream_state.last_error,
            "has_frame": frame is not None,
        }

        if frame is not None:
            item.update({
                "frame_number": frame.frame_number,
                "width": frame.width,
                "height": frame.height,
                "pixel_format": frame.pixel_format,
                "dtype": str(frame.image.dtype),
                "min": int(frame.image.min()),
                "max": int(frame.image.max()),
            })

        result.append(item)

    return jsonify(result)


if __name__ == "__main__":
    initialize()

    try:
        app.run(
            host="0.0.0.0",
            port=5000,
            threaded=True,
        )
    finally:
        broker.stop_all()
        manager.close_all()
