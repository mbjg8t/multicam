from __future__ import annotations

import logging
import io
import os
import time
from pathlib import Path

from flask import Flask, Response, jsonify, render_template, request
from PIL import Image

from multicam.core.cameras import CameraManager, FrameBroker
from multicam.core.provisioning import CameraProvisioningService
from multicam.core.services import (
    AlignmentService,
    CameraProfileStore,
    LiveViewService,
)
from multicam.core.state import (
    AlignmentStateStore,
    CameraLayer,
    ViewStateStore,
)
from multicam.platforms.raspberry_pi import RaspberryPiCameraProvisioner

from .backend_loader import register_available_backends
from .alignment_routes import create_alignment_blueprint


logging.getLogger("werkzeug").setLevel(logging.ERROR)

app = Flask(__name__)

manager = CameraManager()
backend_load_results = register_available_backends(
    manager,
    app.logger,
)

broker = FrameBroker()
state = ViewStateStore()
alignment_state = AlignmentStateStore()
alignment_service = AlignmentService(
    broker=broker,
    state=alignment_state,
)

service = LiveViewService(
    manager=manager,
    broker=broker,
    state=state,
    alignment_state=alignment_state,
)

pi_config_path = os.environ.get(
    "MULTICAM_PI_CONFIG",
    "/boot/firmware/config.txt",
)

provisioning_apply_enabled = (
    os.environ.get("MULTICAM_ALLOW_PROVISIONING_WRITE") == "1"
    and "MULTICAM_PI_CONFIG" in os.environ
    and Path(pi_config_path).resolve()
        != Path("/boot/firmware/config.txt").resolve()
)

provisioning_service = CameraProvisioningService(
    manager=manager,
    provisioner=RaspberryPiCameraProvisioner(
        config_path=pi_config_path,
    ),
)



profile_store = CameraProfileStore()

app.register_blueprint(create_alignment_blueprint(
    manager=manager,
    broker=broker,
    alignment_state=alignment_state,
    alignment_service=alignment_service,
    compositor=service.compositor,
))


def _read_camera_profiles():
    profiles, errors = profile_store.list_profiles()

    for path, error in errors:
        app.logger.warning(
            "Unable to read camera profile %s: %s",
            path,
            error,
        )

    return profiles


def initialize():
    cameras = manager.discover()

    if not cameras:
        app.logger.warning("No cameras discovered")
        return

    opened = []

    for info in cameras:
        try:
            device = manager.open(info.id)
            broker.add_camera(device)
            opened.append(info)
        except Exception:
            app.logger.exception(
                "Unable to open camera %s [%s]",
                info.name,
                info.backend,
            )

    if not opened:
        app.logger.error(
            "Cameras were discovered, but none could be opened"
        )
        return

    # Temporary startup default only. Until camera role/user metadata is
    # persisted, Picamera2 is our best available indication of the visible
    # camera. If none exists, use the first successfully opened camera.
    visible = next(
        (c for c in opened if c.backend == "picamera2"),
        opened[0],
    )

    state.add_layer(
        CameraLayer(
            camera_id=visible.id,
            opacity=1.0,
            z_order=0,
        )
    )

    alignment_target = next(
        (camera for camera in opened if camera.id != visible.id),
        None,
    )

    if alignment_target is not None:
        alignment_state.select(
            visible.id,
            alignment_target.id,
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


def serialize_provisioning():
    snapshot = provisioning_service.inspect()

    return {
        "platform": snapshot.platform,
        "platform_model": snapshot.platform_model,
        "camera_auto_detect": snapshot.camera_auto_detect,
        "pending_changes": snapshot.pending_changes,
        "reboot_required": snapshot.reboot_required,
        "apply_enabled": provisioning_apply_enabled,
        "errors": snapshot.errors,
        "proposed_changes": [
            {
                "action": change.action,
                "description": change.description,
                "overlay": change.overlay,
                "parameters": change.parameters,
                "reboot_required": change.reboot_required,
            }
            for change in snapshot.proposed_changes
        ],
        "entries": [
            {
                "status": entry.status.value,
                "message": entry.message,
                "runtime": (
                    {
                        "runtime_id": entry.runtime.runtime_id,
                        "backend": entry.runtime.backend,
                        "name": entry.runtime.name,
                        "model": entry.runtime.model,
                        "connected": entry.runtime.connected,
                        "runtime_number": entry.runtime.runtime_number,
                        "runtime_path": entry.runtime.runtime_path,
                        "rotation": entry.runtime.rotation,
                    }
                    if entry.runtime is not None
                    else None
                ),
                "configured": (
                    {
                        "overlay": entry.configured.overlay,
                        "parameters": entry.configured.parameters,
                        "port_hint": entry.configured.port_hint,
                        "line_number": entry.configured.line_number,
                    }
                    if entry.configured is not None
                    else None
                ),
            }
            for entry in snapshot.entries
        ],
    }


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/cameras")
def cameras_page():
    return render_template("cameras.html")


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


@app.route("/api/backends")
def backends_api():
    discovery_errors = manager.backend_errors

    return jsonify([
        {
            "name": result.name,
            "loaded": result.loaded,
            "load_error": result.error,
            "discovery_error": discovery_errors.get(result.name),
        }
        for result in backend_load_results
    ])


@app.route(
    "/api/camera-profiles",
    methods=["GET"],
)
def camera_profiles_api():
    return jsonify({
        "profiles": _read_camera_profiles(),
    })


@app.route(
    "/api/camera-profiles",
    methods=["POST"],
)
def save_camera_profile_api():
    data = request.get_json(silent=True) or {}

    name = str(data.get("name", "")).strip()
    camera_id = data.get("camera_id")

    if not name:
        return jsonify({
            "error": "Profile name is required"
        }), 400

    if not camera_id:
        return jsonify({
            "error": "camera_id is required"
        }), 400

    device = manager.get_device(camera_id)

    if device is None:
        return jsonify({
            "error": "Camera is not open"
        }), 404

    try:
        info = manager.get_camera_info(camera_id)
    except KeyError:
        return jsonify({
            "error": "Unknown camera"
        }), 404

    controls = {}

    for capability in device.get_capabilities():
        if not capability.writable:
            continue

        # Camera Profiles v1 only stores controls that can
        # safely be changed while the camera is already open.
        if capability.metadata.get(
            "requires_stream_restart"
        ):
            continue

        try:
            controls[capability.id] = (
                device.get_control(capability.id)
            )
        except Exception:
            app.logger.exception(
                "Unable to read camera control %s:%s",
                camera_id,
                capability.id,
            )

    profile = {
        "name": name,
        "camera": {
            "vendor": info.vendor,
            "model": info.model,
            "backend": info.backend,
        },
        "controls": controls,
    }

    try:
        profile_store.save(name, profile)

    except (OSError, ValueError) as exc:
        return jsonify({
            "error": str(exc)
        }), 400

    return jsonify({
        "success": True,
        "profile": profile,
    })


@app.route(
    "/api/camera-profiles/<path:profile_name>/load",
    methods=["POST"],
)
def load_camera_profile_api(profile_name):
    data = request.get_json(silent=True) or {}
    camera_id = data.get("camera_id")

    if not camera_id:
        return jsonify({
            "error": "camera_id is required"
        }), 400

    device = manager.get_device(camera_id)

    if device is None:
        return jsonify({
            "error": "Camera is not open"
        }), 404

    try:
        profile = profile_store.load(profile_name)

    except FileNotFoundError:
        return jsonify({
            "error": "Profile not found"
        }), 404

    except (OSError, ValueError) as exc:
        return jsonify({
            "error": str(exc)
        }), 400

    capabilities = {
        capability.id: capability
        for capability in device.get_capabilities()
    }

    applied = []
    skipped = []
    errors = []

    for control_id, value in (
        profile.get("controls", {}).items()
    ):
        capability = capabilities.get(control_id)

        if capability is None:
            skipped.append({
                "control_id": control_id,
                "reason": "Unsupported by this camera",
            })
            continue

        if not capability.writable:
            skipped.append({
                "control_id": control_id,
                "reason": "Read only",
            })
            continue

        if capability.metadata.get(
            "requires_stream_restart"
        ):
            skipped.append({
                "control_id": control_id,
                "reason": "Requires stream restart",
            })
            continue

        try:
            device.set_control(
                control_id,
                value,
            )

            applied.append(control_id)

        except Exception as exc:
            errors.append({
                "control_id": control_id,
                "error": str(exc),
            })

    return jsonify({
        "success": len(errors) == 0,
        "profile": profile.get(
            "name",
            profile_name,
        ),
        "applied": applied,
        "skipped": skipped,
        "errors": errors,
    })


@app.route(
    "/api/camera-profiles/<path:profile_name>",
    methods=["DELETE"],
)
def delete_camera_profile_api(profile_name):
    try:
        if not profile_store.delete(profile_name):
            return jsonify({
                "error": "Profile not found"
            }), 404

    except (OSError, ValueError) as exc:
        return jsonify({
            "error": str(exc)
        }), 400

    return jsonify({
        "success": True,
    })


@app.route(
    "/api/cameras/<path:camera_id>/capabilities"
)
def camera_capabilities_api(camera_id):
    device = manager.get_device(camera_id)

    if device is None:
        return jsonify({
            "error": "Camera is not open"
        }), 404

    try:
        capabilities = device.get_capabilities()
    except Exception as exc:
        app.logger.exception(
            "Unable to read capabilities for camera %s",
            camera_id,
        )
        return jsonify({"error": str(exc)}), 500

    result = []

    for capability in capabilities:
        current_value = capability.value

        if capability.readable:
            try:
                current_value = device.get_control(capability.id)
            except Exception:
                app.logger.debug(
                    "Unable to read camera control %s:%s",
                    camera_id,
                    capability.id,
                    exc_info=True,
                )

        result.append({
            "id": capability.id,
            "name": capability.name,
            "type": capability.type,
            "readable": capability.readable,
            "writable": capability.writable,
            "value": capability.value,
            "current_value": current_value,
            "minimum": capability.minimum,
            "maximum": capability.maximum,
            "step": capability.step,
            "choices": capability.choices,
            "units": capability.units,
            "metadata": capability.metadata,
        })

    return jsonify({
        "camera_id": camera_id,
        "capabilities": result,
    })


@app.route(
    "/api/cameras/<path:camera_id>/controls",
    methods=["POST"],
)
def camera_controls_api(camera_id):
    device = manager.get_device(camera_id)

    if device is None:
        return jsonify({
            "error": "Camera is not open"
        }), 404

    data = request.get_json(force=True)
    control_id = data.get("control_id")

    if not control_id:
        return jsonify({
            "error": "control_id is required"
        }), 400

    capabilities = {
        capability.id: capability
        for capability in device.get_capabilities()
    }

    capability = capabilities.get(control_id)

    if capability is None:
        return jsonify({
            "error": "Unknown camera control"
        }), 404

    if not capability.writable:
        return jsonify({
            "error": "Camera control is read-only"
        }), 400

    value = data.get("value")

    try:
        device.set_control(control_id, value)
        current_value = (
            device.get_control(control_id)
            if capability.readable
            else value
        )
    except Exception as exc:
        app.logger.exception(
            "Unable to set camera control %s:%s",
            camera_id,
            control_id,
        )
        return jsonify({"error": str(exc)}), 500

    return jsonify({
        "camera_id": camera_id,
        "control_id": control_id,
        "value": current_value,
    })


@app.route("/api/state")
def state_api():
    return jsonify(serialize_state())


@app.route("/api/hardware")
def hardware_api():
    return jsonify(serialize_provisioning())


@app.route("/api/hardware/apply", methods=["POST"])
def hardware_apply_api():
    if not provisioning_apply_enabled:
        return jsonify({
            "success": False,
            "error": (
                "Provisioning writes are disabled. "
                "Test writes require an alternate MULTICAM_PI_CONFIG "
                "and MULTICAM_ALLOW_PROVISIONING_WRITE=1."
            ),
        }), 403

    snapshot = provisioning_service.inspect()

    if not snapshot.proposed_changes:
        return jsonify({
            "success": True,
            "applied_changes": [],
            "skipped_changes": [],
            "backup_path": None,
            "reboot_required": False,
            "errors": [],
        })

    result = provisioning_service.apply(
        snapshot.proposed_changes
    )

    return jsonify({
        "success": result.success,
        "applied_changes": [
            {
                "action": change.action,
                "description": change.description,
                "overlay": change.overlay,
                "parameters": change.parameters,
                "reboot_required": change.reboot_required,
            }
            for change in result.applied_changes
        ],
        "skipped_changes": [
            {
                "action": change.action,
                "description": change.description,
                "overlay": change.overlay,
                "parameters": change.parameters,
                "reboot_required": change.reboot_required,
            }
            for change in result.skipped_changes
        ],
        "backup_path": result.backup_path,
        "reboot_required": result.reboot_required,
        "errors": result.errors,
    }), (200 if result.success else 500)


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


def main():
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


if __name__ == "__main__":
    main()
