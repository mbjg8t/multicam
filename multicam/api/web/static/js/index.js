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
        strip.append(chip);
    }
}

function renderAlignmentState() {
    renderCameraStrip();
}

async function refreshAlignment() {
    try {
        alignmentState = await alignmentApi('/api/alignment');
        renderAlignmentState();
    } catch (error) {
        console.error('Unable to load camera status:', error);
    }
}

document.getElementById('open-alignment').addEventListener('click', () => {
    window.open('/alignment', 'multicam-alignment');
});

document.getElementById('open-focus').addEventListener('click', () => {
    window.open('/focus', 'multicam-focus');
});

document.getElementById('open-dsp').addEventListener('click', () => {
    window.open('/dsp', 'multicam-dsp');
});

const viewer = document.getElementById('viewer');
const liveImage = document.getElementById('live-image');
const frozenImage = document.getElementById('frozen-image');
const captureLive = document.getElementById('capture-live');
const freezeLive = document.getElementById('freeze-live');
const zoomLabel = document.getElementById('zoom-label');
const MIN_ZOOM = 1;
const MAX_ZOOM = 16;
let zoom = 1;
let panX = 0;
let panY = 0;
let dragStart = null;
let liveFrozen = false;

function renderZoom() {
    const transform = `translate(${panX}px, ${panY}px) scale(${zoom})`;
    liveImage.style.transform = transform;
    frozenImage.style.transform = transform;
    zoomLabel.textContent = `${Math.round(zoom * 100)}%`;
    viewer.classList.toggle('zoomed', zoom > 1.001);
}

function setZoom(nextZoom, clientX = null, clientY = null) {
    nextZoom = Math.min(MAX_ZOOM, Math.max(MIN_ZOOM, nextZoom));
    if (Math.abs(nextZoom - zoom) < 0.0001) return;

    if (clientX !== null && clientY !== null) {
        const bounds = viewer.getBoundingClientRect();
        const pointerX = clientX - (bounds.left + bounds.width / 2);
        const pointerY = clientY - (bounds.top + bounds.height / 2);
        const ratio = nextZoom / zoom;
        panX = pointerX - (pointerX - panX) * ratio;
        panY = pointerY - (pointerY - panY) * ratio;
    } else if (nextZoom === MIN_ZOOM) {
        panX = 0;
        panY = 0;
    }

    zoom = nextZoom;
    renderZoom();
}

function resetZoom() {
    zoom = 1;
    panX = 0;
    panY = 0;
    renderZoom();
}

viewer.addEventListener('wheel', event => {
    event.preventDefault();
    const factor = Math.exp(-event.deltaY * 0.0015);
    setZoom(zoom * factor, event.clientX, event.clientY);
}, {passive: false});

viewer.addEventListener('pointerdown', event => {
    if (event.target.closest('.zoom-controls')) return;
    if (zoom <= 1) return;
    dragStart = {x: event.clientX, y: event.clientY, panX, panY};
    viewer.setPointerCapture(event.pointerId);
    viewer.classList.add('dragging');
});

viewer.addEventListener('pointermove', event => {
    if (!dragStart) return;
    panX = dragStart.panX + event.clientX - dragStart.x;
    panY = dragStart.panY + event.clientY - dragStart.y;
    renderZoom();
});

function endDrag(event) {
    if (!dragStart) return;
    dragStart = null;
    viewer.classList.remove('dragging');
    if (viewer.hasPointerCapture(event.pointerId)) {
        viewer.releasePointerCapture(event.pointerId);
    }
}

viewer.addEventListener('pointerup', endDrag);
viewer.addEventListener('pointercancel', endDrag);
viewer.addEventListener('dblclick', event => {
    if (!event.target.closest('.zoom-controls')) resetZoom();
});

captureLive.addEventListener('click', async () => {
    captureLive.disabled = true;
    try {
        const response = await fetch('/api/live/capture');
        if (!response.ok) {
            throw new Error(`Capture failed: ${response.status}`);
        }
        const blob = await response.blob();
        const disposition = response.headers.get('Content-Disposition') || '';
        const match = disposition.match(/filename="?([^";]+)"?/i);
        const link = document.createElement('a');
        link.href = URL.createObjectURL(blob);
        link.download = match ? match[1] : 'multicam-capture.jpg';
        document.body.appendChild(link);
        link.click();
        link.remove();
        URL.revokeObjectURL(link.href);
    } catch (error) {
        console.error(error);
        window.alert('Unable to save live capture.');
    } finally {
        captureLive.disabled = false;
    }
});

freezeLive.addEventListener('click', () => {
    if (!liveFrozen) {
        if (!liveImage.naturalWidth || !liveImage.naturalHeight) return;
        frozenImage.width = liveImage.naturalWidth;
        frozenImage.height = liveImage.naturalHeight;
        frozenImage.getContext('2d').drawImage(
            liveImage, 0, 0, frozenImage.width, frozenImage.height
        );
        frozenImage.style.display = 'block';
        liveImage.style.display = 'none';
        liveFrozen = true;
        freezeLive.textContent = 'Resume';
        freezeLive.title = 'Resume live video';
    } else {
        frozenImage.style.display = 'none';
        liveImage.style.display = 'block';
        liveFrozen = false;
        freezeLive.textContent = 'Freeze';
        freezeLive.title = 'Freeze the displayed live frame';
    }
    renderZoom();
});
document.getElementById('zoom-in').addEventListener('click', () => setZoom(zoom * 1.25));
document.getElementById('zoom-out').addEventListener('click', () => setZoom(zoom / 1.25));
document.getElementById('zoom-fit').addEventListener('click', resetZoom);

renderZoom();

refreshAlignment();
setInterval(refreshAlignment, 1500);
