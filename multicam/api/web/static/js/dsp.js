let dspState = null;
let selectedCameraId = null;
let updateTimer = null;
let applyingState = false;

const cameraSelect = document.getElementById('dsp-camera');

async function api(path, options = {}) {
    const response = await fetch(path, options);
    const data = await response.json();
    if (!response.ok) throw new Error(data.error || response.statusText);
    return data;
}

function selectedCamera() {
    return dspState?.cameras.find(camera => camera.id === selectedCameraId);
}

function cameraLabel(camera) {
    const model = camera.model ? ` — ${camera.model}` : '';
    return `${camera.name}${model}`;
}

function setRange(id, outputId, value, digits = 1) {
    document.getElementById(id).value = value;
    document.getElementById(outputId).textContent =
        Number(value).toFixed(digits);
}

function applyConfigToControls() {
    const camera = selectedCamera();
    if (!camera) return;
    const config = camera.config;
    applyingState = true;
    document.getElementById('dsp-enabled').checked = config.enabled;
    setRange('black-percentile', 'black-value', config.black_percentile);
    setRange('white-percentile', 'white-value', config.white_percentile);
    setRange('gamma', 'gamma-value', config.gamma, 2);
    setRange('denoise-radius', 'denoise-value', config.denoise_radius, 0);
    setRange('sharpen', 'sharpen-value', config.sharpen, 2);
    setRange('max-fps', 'fps-value', config.max_fps, 0);
    document.getElementById('palette').value = config.palette;
    document.getElementById('grayscale').checked = config.grayscale;
    document.getElementById('invert').checked = config.invert;
    applyingState = false;
    updatePreviews();
    renderStatus();
}

function updatePreviews() {
    if (!selectedCameraId) return;
    const suffix = `?t=${Date.now()}`;
    const id = encodeURIComponent(selectedCameraId);
    document.getElementById('raw-preview').src = `/dsp/stream/raw/${id}${suffix}`;
    document.getElementById('processed-preview').src =
        `/dsp/stream/processed/${id}${suffix}`;
}

function renderStatus() {
    const camera = selectedCamera();
    const status = document.getElementById('dsp-status');
    if (!camera) {
        status.textContent = 'No running cameras';
        return;
    }
    if (camera.status.last_error) {
        status.textContent = `DSP error: ${camera.status.last_error}`;
        return;
    }
    if (!camera.config.enabled) {
        status.textContent = 'DSP bypassed — live view uses raw frame';
        return;
    }
    const latency = camera.status.latency_ms === null
        ? 'waiting'
        : `${camera.status.latency_ms.toFixed(1)} ms`;
    status.textContent =
        `DSP ${camera.status.running ? 'running' : 'starting'} | ` +
        `${camera.status.actual_fps.toFixed(1)} FPS | ${latency}`;
}

function populateCameras() {
    cameraSelect.replaceChildren();
    for (const camera of dspState.cameras) {
        const option = document.createElement('option');
        option.value = camera.id;
        option.textContent = cameraLabel(camera);
        option.disabled = !camera.running || !camera.has_frame;
        cameraSelect.append(option);
    }
    if (!selectedCameraId || !dspState.cameras.some(c => c.id === selectedCameraId)) {
        selectedCameraId = dspState.cameras.find(c => c.running && c.has_frame)?.id ||
            dspState.cameras[0]?.id || null;
    }
    cameraSelect.value = selectedCameraId || '';
}

function configFromControls() {
    return {
        enabled: document.getElementById('dsp-enabled').checked,
        black_percentile: Number(document.getElementById('black-percentile').value),
        white_percentile: Number(document.getElementById('white-percentile').value),
        gamma: Number(document.getElementById('gamma').value),
        denoise_radius: Number(document.getElementById('denoise-radius').value),
        sharpen: Number(document.getElementById('sharpen').value),
        max_fps: Number(document.getElementById('max-fps').value),
        palette: document.getElementById('palette').value,
        grayscale: document.getElementById('grayscale').checked,
        invert: document.getElementById('invert').checked
    };
}

async function saveConfig() {
    if (!selectedCameraId) return;
    try {
        const camera = await api(`/api/dsp/${encodeURIComponent(selectedCameraId)}`, {
            method: 'PATCH',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify(configFromControls())
        });
        const index = dspState.cameras.findIndex(item => item.id === camera.id);
        dspState.cameras[index] = camera;
        renderStatus();
    } catch (error) {
        document.getElementById('dsp-status').textContent = error.message;
    }
}

function scheduleSave() {
    if (applyingState) return;
    updateReadouts();
    clearTimeout(updateTimer);
    updateTimer = setTimeout(saveConfig, 120);
}

function updateReadouts() {
    const mappings = [
        ['black-percentile', 'black-value', 1],
        ['white-percentile', 'white-value', 1],
        ['gamma', 'gamma-value', 2],
        ['denoise-radius', 'denoise-value', 0],
        ['sharpen', 'sharpen-value', 2],
        ['max-fps', 'fps-value', 0]
    ];
    for (const [inputId, outputId, digits] of mappings) {
        document.getElementById(outputId).textContent =
            Number(document.getElementById(inputId).value).toFixed(digits);
    }
}

async function refresh(preserveControls = true) {
    dspState = await api('/api/dsp');
    populateCameras();
    if (!preserveControls) applyConfigToControls();
    else renderStatus();
}

cameraSelect.addEventListener('change', () => {
    selectedCameraId = cameraSelect.value;
    applyConfigToControls();
});

document.querySelectorAll(
    '.controls input, .controls select, #dsp-enabled'
).forEach(control => control.addEventListener('input', scheduleSave));

document.getElementById('reset-dsp').addEventListener('click', async () => {
    if (!selectedCameraId) return;
    const camera = await api(`/api/dsp/${encodeURIComponent(selectedCameraId)}`, {
        method: 'PATCH',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({
            enabled: false,
            black_percentile: 0,
            white_percentile: 100,
            gamma: 1,
            denoise_radius: 0,
            sharpen: 0,
            grayscale: false,
            invert: false,
            palette: 'normal',
            max_fps: 15
        })
    });
    const index = dspState.cameras.findIndex(item => item.id === camera.id);
    dspState.cameras[index] = camera;
    applyConfigToControls();
});

refresh(false).catch(error => {
    document.getElementById('dsp-status').textContent = error.message;
});
setInterval(() => refresh(true).catch(console.error), 1000);
