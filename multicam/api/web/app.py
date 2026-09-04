from __future__ import annotations

import logging

import io
import time

from flask import Flask, Response, jsonify, request
from PIL import Image

from multicam.backends.aravis import AravisBackend
from multicam.backends.picamera2 import Picamera2Backend
from multicam.core.cameras import CameraManager, FrameBroker
from multicam.core.services import LiveViewService
from multicam.core.state import CameraLayer, ViewStateStore


logging.getLogger("werkzeug").setLevel(logging.ERROR)

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

    # Temporary startup default only. Until camera role/user metadata is
    # persisted, Picamera2 is our best available indication of the visible
    # camera. If none exists, use the first discovered camera.
    visible = next(
        (c for c in cameras if c.backend == "picamera2"),
        cameras[0],
    )

    state.add_layer(
        CameraLayer(
            camera_id=visible.id,
            opacity=1.0,
            z_order=0,
        )
    )

    broker.start_all()


def serialize_state():
    current = state.get()

    return {
        "layers": [
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
            for layer in current.layers
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

        button:hover:not(:disabled) {
            background: #555;
        }

        button:disabled {
            opacity: 0.45;
            cursor: default;
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

            <button disabled>Alignment</button>
            <button disabled>MTF</button>
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
    return r"""
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

        .layer {
            border-top: 1px solid #444;
            padding: 14px 0;
        }

        .layer:first-child {
            border-top: none;
        }

        .layer-title {
            display: flex;
            align-items: center;
            gap: 10px;
        }

        .layer-number {
            color: #aaa;
            min-width: 58px;
        }

        .camera-info {
            font-size: 13px;
            color: #aaa;
            margin-top: 6px;
        }

        .stream-ok {
            color: #8f8;
        }

        .stream-error {
            color: #f88;
        }

        .row {
            display: flex;
            align-items: center;
            gap: 12px;
            margin: 10px 0 4px 0;
            flex-wrap: wrap;
        }

        select,
        input[type="range"] {
            margin-top: 4px;
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

        button:hover:not(:disabled) {
            background: #555;
        }

        button:disabled {
            opacity: 0.45;
            cursor: default;
        }

        .opacity {
            width: 260px;
        }

        .value {
            width: 45px;
        }

        .spacer {
            flex: 1;
        }

        .status {
            color: #8f8;
            font-size: 13px;
            min-height: 18px;
        }

        .empty {
            color: #aaa;
            padding: 10px 0;
        }
    </style>
</head>

<body>

<h2>Cameras</h2>

<div class="section">
    <strong>Camera Layers</strong>
    <div id="layerList"></div>
</div>

<div class="section">
    <strong>Add Camera Layer</strong>

    <div class="row">
        <select id="availableCamera"></select>
        <button id="addLayerButton" onclick="addLayer()">
            + Add Camera Layer
        </button>
    </div>

    <div class="camera-info">
        The first visible camera is Layer 1 by default. Every layer uses the
        same enable and opacity controls.
    </div>
</div>

<div id="status" class="status"></div>

<script>

let cameras = [];
let streams = [];
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
    [cameras, streams, viewState] = await Promise.all([
        api('/api/cameras'),
        api('/api/streams'),
        api('/api/state')
    ]);

    renderLayers();
    renderAvailableCameras();
}


function cameraById(id) {
    return cameras.find(c => c.id === id);
}


function streamById(id) {
    return streams.find(s => s.id === id);
}


function cameraLabel(camera) {
    if (!camera) {
        return 'Unknown camera';
    }

    return `${camera.name} [${camera.backend}]`;
}


function streamText(stream) {
    if (!stream) {
        return 'No stream status';
    }

    if (stream.last_error) {
        return `ERROR: ${stream.last_error}`;
    }

    if (!stream.running) {
        return 'Stream stopped';
    }

    if (!stream.has_frame) {
        return `Running - waiting for frame (${stream.frame_count} frames)`;
    }

    const details = [
        `${stream.width}x${stream.height}`,
        stream.pixel_format,
        stream.dtype,
        `${stream.frame_count} frames`
    ].filter(Boolean);

    return `Streaming - ${details.join(' | ')}`;
}


function renderLayers() {
    const container = document.getElementById('layerList');
    container.innerHTML = '';

    if (viewState.layers.length === 0) {
        container.innerHTML =
            '<div class="empty">No camera layers</div>';
        return;
    }

    const layers = [...viewState.layers].sort(
        (a, b) => a.z_order - b.z_order
    );

    layers.forEach((layer, index) => {
        const camera = cameraById(layer.camera_id);
        const stream = streamById(layer.camera_id);
        const streamClass =
            stream && stream.running && !stream.last_error
                ? 'stream-ok'
                : 'stream-error';

        const div = document.createElement('div');
        div.className = 'layer';

        div.innerHTML = `
            <div class="layer-title">
                <span class="layer-number">Layer ${index + 1}</span>
                <strong>${cameraLabel(camera)}</strong>
            </div>

            <div class="camera-info">
                ${camera ? `${camera.vendor || ''} ${camera.model || ''}`.trim() : ''}
                ${camera && camera.serial ? ` | Serial ${camera.serial}` : ''}
            </div>

            <div class="camera-info ${streamClass}">
                ${escapeHtml(streamText(stream))}
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

                <span class="spacer"></span>

                <button disabled title="Camera settings are the next step">
                    Settings
                </button>

                <button onclick="removeLayer(
                    '${escapeJs(layer.camera_id)}'
                )">
                    Remove
                </button>
            </div>
        `;

        container.appendChild(div);
    });
}


function renderAvailableCameras() {
    const select = document.getElementById('availableCamera');
    const button = document.getElementById('addLayerButton');

    const used = new Set(
        viewState.layers.map(layer => layer.camera_id)
    );

    const available = cameras.filter(
        camera => !used.has(camera.id)
    );

    select.innerHTML = '';

    if (available.length === 0) {
        const option = document.createElement('option');
        option.textContent = 'No unused cameras available';
        option.value = '';
        select.appendChild(option);
        select.disabled = true;
        button.disabled = true;
        return;
    }

    select.disabled = false;
    button.disabled = false;

    for (const camera of available) {
        const option = document.createElement('option');
        option.value = camera.id;
        option.textContent = cameraLabel(camera);
        select.appendChild(option);
    }
}


function escapeJs(value) {
    return value
        .replace(/\\/g, '\\\\')
        .replace(/'/g, "\\'");
}


function escapeHtml(value) {
    return String(value)
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;')
        .replace(/'/g, '&#039;');
}


async function addLayer() {
    const select = document.getElementById('availableCamera');
    const cameraId = select.value;

    if (!cameraId) {
        return;
    }

    await api('/api/layers', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json'
        },
        body: JSON.stringify({
            camera_id: cameraId,
            opacity: 0.5
        })
    });

    await refresh();
    showStatus('Camera layer added');
}


async function removeLayer(cameraId) {
    await api(
        '/api/layers/' + encodeURIComponent(cameraId),
        {method: 'DELETE'}
    );

    await refresh();
    showStatus('Camera layer removed');
}


async function setOpacity(cameraId, value) {
    viewState = await api(
        '/api/layers/' + encodeURIComponent(cameraId),
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

    showStatus('Opacity updated');
}


async function setEnabled(cameraId, enabled) {
    viewState = await api(
        '/api/layers/' + encodeURIComponent(cameraId),
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

    showStatus(enabled ? 'Camera layer enabled' : 'Camera layer disabled');
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

// Keep diagnostics fresh without changing layer controls/state.
setInterval(() => {
    refresh().catch(console.error);
}, 2000);

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


@app.route("/api/layers", methods=["POST"])
def add_layer_api():
    data = request.get_json(force=True)

    camera_id = data.get("camera_id")
    opacity = float(data.get("opacity", 0.5))

    known_ids = {
        camera.id
        for camera in manager.list_cameras()
    }

    if camera_id not in known_ids:
        return jsonify({"error": "Unknown camera"}), 404

    current = state.get()

    if any(
        layer.camera_id == camera_id
        for layer in current.layers
    ):
        return jsonify({
            "error": "Camera is already a layer"
        }), 400

    next_z = max(
        (layer.z_order for layer in current.layers),
        default=-1,
    ) + 1

    state.add_layer(
        CameraLayer(
            camera_id=camera_id,
            opacity=opacity,
            z_order=next_z,
        )
    )

    return jsonify(serialize_state())


@app.route(
    "/api/layers/<path:camera_id>",
    methods=["PATCH"],
)
def update_layer_api(camera_id):
    data = request.get_json(force=True)

    try:
        state.update_layer(
            camera_id,
            enabled=data.get("enabled"),
            opacity=data.get("opacity"),
        )
    except KeyError:
        return jsonify({"error": "Layer not found"}), 404

    return jsonify(serialize_state())


@app.route(
    "/api/layers/<path:camera_id>",
    methods=["DELETE"],
)
def remove_layer_api(camera_id):
    state.remove_layer(camera_id)
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
