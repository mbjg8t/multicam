let alignmentState = null;

async function alignmentApi(path, options = {}) {
    const response = await fetch(path, options);
    const data = await response.json();

    if (!response.ok) {
        throw new Error(data.error || `Request failed: ${response.status}`);
    }

    return data;
}

function cameraLabel(camera) {
    return camera.model
        ? `${camera.name} — ${camera.model}`
        : camera.name;
}

function fillSelect(element, selectedId, otherId) {
    const priorFocus = document.activeElement === element;
    element.replaceChildren();

    for (const camera of alignmentState.cameras) {
        const option = document.createElement('option');
        option.value = camera.id;
        option.textContent = cameraLabel(camera);
        option.disabled = (
            !camera.running || !camera.has_frame || camera.id === otherId
        );
        option.selected = camera.id === selectedId;
        element.append(option);
    }

    element.disabled = alignmentState.cameras.length < 2;

    if (priorFocus) {
        element.focus();
    }
}

function renderCameraStrip() {
    const strip = document.getElementById('camera-strip');
    strip.replaceChildren();

    if (alignmentState.cameras.length === 0) {
        strip.textContent = 'No cameras discovered';
        return;
    }

    for (const camera of alignmentState.cameras) {
        const chip = document.createElement('button');
        chip.type = 'button';
        chip.className = 'camera-chip';

        if (camera.role) {
            chip.classList.add(camera.role);
        }
        if (camera.alignment_status === 'mode_mismatch') {
            chip.classList.add('mode-mismatch');
        }

        const dot = document.createElement('span');
        dot.className = 'status-dot';
        dot.classList.add(
            camera.last_error
                ? 'error'
                : camera.running && camera.has_frame
                    ? 'running'
                    : camera.connected
                        ? 'waiting'
                        : 'offline'
        );

        const name = document.createTextNode(cameraLabel(camera));
        const badge = document.createElement('span');
        badge.className = 'role-badge';
        badge.textContent = camera.role || '';
        const alignmentBadge = document.createElement('span');
        alignmentBadge.className = 'alignment-badge';
        alignmentBadge.textContent = (
            camera.alignment_status === 'reference'
                ? ''
                : camera.alignment_status.replace('_', ' ')
        );

        chip.append(dot, name, badge, alignmentBadge);
        chip.title = camera.last_error || camera.alignment_status;
        chip.disabled = !camera.running || !camera.has_frame;
        chip.addEventListener('click', () => selectTarget(camera.id));
        strip.append(chip);
    }
}

function renderAlignmentState() {
    fillSelect(
        document.getElementById('reference-camera'),
        alignmentState.reference_camera_id,
        alignmentState.target_camera_id
    );
    fillSelect(
        document.getElementById('target-camera'),
        alignmentState.target_camera_id,
        alignmentState.reference_camera_id
    );
    renderCameraStrip();
}

async function updateSelection(referenceId, targetId) {
    if (!referenceId || !targetId || referenceId === targetId) {
        return;
    }

    try {
        alignmentState = await alignmentApi('/api/alignment/selection', {
            method: 'PATCH',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({
                reference_camera_id: referenceId,
                target_camera_id: targetId
            })
        });
        renderAlignmentState();
    } catch (error) {
        window.alert(error.message);
        await refreshAlignment();
    }
}

function selectTarget(cameraId) {
    if (!alignmentState || cameraId === alignmentState.reference_camera_id) {
        return;
    }
    updateSelection(alignmentState.reference_camera_id, cameraId);
}

async function refreshAlignment() {
    try {
        alignmentState = await alignmentApi('/api/alignment');
        renderAlignmentState();
    } catch (error) {
        console.error('Unable to load camera status:', error);
    }
}

document.getElementById('reference-camera').addEventListener('change', event => {
    updateSelection(event.target.value, alignmentState.target_camera_id);
});

document.getElementById('target-camera').addEventListener('change', event => {
    updateSelection(alignmentState.reference_camera_id, event.target.value);
});

document.getElementById('open-alignment').addEventListener('click', () => {
    window.open('/alignment', 'multicam-alignment');
});

document.getElementById('open-focus').addEventListener('click', () => {
    window.open('/focus', 'multicam-focus');
});

document.getElementById('open-dsp').addEventListener('click', () => {
    window.open('/dsp', 'multicam-dsp');
});

refreshAlignment();
setInterval(refreshAlignment, 1500);
