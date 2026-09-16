let dspState = null;
let selectedCameraId = null;
let updateTimer = null;
let applyingState = false;
let saveInFlight = false;
let savePending = false;
let lastSaveStarted = 0;

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
    document.getElementById('levels-mode').value = config.levels_mode;
    setRange('black-percentile', 'black-value', config.black_percentile);
    setRange('white-percentile', 'white-value', config.white_percentile);
    document.getElementById('gamma-mode').value = config.gamma_mode;
    setRange('gamma', 'gamma-value', config.gamma, 2);
    document.getElementById('denoise-mode').value = config.denoise_mode;
    setRange('denoise-radius', 'denoise-value', config.denoise_radius, 0);
    document.getElementById('sharpen-mode').value = config.sharpen_mode;
    setRange('sharpen', 'sharpen-value', config.sharpen, 2);
    document.getElementById('edge-mode').value = config.edge_mode;
    setRange('edge-strength', 'edge-value', config.edge_strength, 2);
    setRange('max-fps', 'fps-value', config.max_fps, 0);
    document.getElementById('palette').value = config.palette;
    document.getElementById('invert').value = String(config.invert);
    applyingState = false;
    updateControlAvailability();
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
        levels_mode: document.getElementById('levels-mode').value,
        black_percentile: Number(document.getElementById('black-percentile').value),
        white_percentile: Number(document.getElementById('white-percentile').value),
        gamma_mode: document.getElementById('gamma-mode').value,
        gamma: Number(document.getElementById('gamma').value),
        denoise_mode: document.getElementById('denoise-mode').value,
        denoise_radius: Number(document.getElementById('denoise-radius').value),
        sharpen_mode: document.getElementById('sharpen-mode').value,
        sharpen: Number(document.getElementById('sharpen').value),
        edge_mode: document.getElementById('edge-mode').value,
        edge_strength: Number(document.getElementById('edge-strength').value),
        max_fps: Number(document.getElementById('max-fps').value),
        palette: document.getElementById('palette').value,
        invert: document.getElementById('invert').value === 'true'
    };
}

async function saveConfig() {
    if (!selectedCameraId || saveInFlight) {
        savePending = true;
        return;
    }
    saveInFlight = true;
    savePending = false;
    lastSaveStarted = performance.now();
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
    } finally {
        saveInFlight = false;
        if (savePending) scheduleSave(true);
    }
}

function scheduleSave(immediate = false) {
    if (applyingState) return;
    updateReadouts();
    updateControlAvailability();
    savePending = true;

    if (updateTimer !== null || saveInFlight) return;

    const elapsed = performance.now() - lastSaveStarted;
    const delay = immediate ? 0 : Math.max(0, 50 - elapsed);
    updateTimer = setTimeout(() => {
        updateTimer = null;
        saveConfig();
    }, delay);
}

function updateReadouts() {
    const mappings = [
        ['black-percentile', 'black-value', 1],
        ['white-percentile', 'white-value', 1],
        ['gamma', 'gamma-value', 2],
        ['denoise-radius', 'denoise-value', 0],
        ['sharpen', 'sharpen-value', 2],
        ['edge-strength', 'edge-value', 2],
        ['max-fps', 'fps-value', 0]
    ];
    for (const [inputId, outputId, digits] of mappings) {
        document.getElementById(outputId).textContent =
            Number(document.getElementById(inputId).value).toFixed(digits);
    }
}

function setStageActive(modeId, inputIds, activeValue = null) {
    const mode = document.getElementById(modeId).value;
    const active = activeValue === null ? mode !== 'off' : mode === activeValue;

    for (const inputId of inputIds) {
        const input = document.getElementById(inputId);
        input.disabled = !active;
        input.closest('div')?.classList.toggle('inactive', !active);
    }
}

function updateControlAvailability() {
    setStageActive(
        'levels-mode',
        ['black-percentile', 'white-percentile'],
        'percentile'
    );
    document.getElementById('levels-controls').classList.toggle(
        'inactive',
        document.getElementById('levels-mode').value !== 'percentile'
    );
    setStageActive('gamma-mode', ['gamma']);
    setStageActive('denoise-mode', ['denoise-radius']);
    setStageActive('sharpen-mode', ['sharpen']);
    setStageActive('edge-mode', ['edge-strength']);
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
).forEach(control => control.addEventListener('input', () => scheduleSave()));

document.querySelectorAll('.controls select, #dsp-enabled').forEach(control => {
    control.addEventListener('change', () => {
        if (control.id === 'denoise-mode' && control.value !== 'off' &&
            Number(document.getElementById('denoise-radius').value) === 0) {
            document.getElementById('denoise-radius').value = 1;
        }
        if (control.id === 'sharpen-mode' && control.value !== 'off' &&
            Number(document.getElementById('sharpen').value) === 0) {
            document.getElementById('sharpen').value = 1;
        }
        scheduleSave(true);
    });
});

document.getElementById('reset-dsp').addEventListener('click', async () => {
    if (!selectedCameraId) return;
    const camera = await api(`/api/dsp/${encodeURIComponent(selectedCameraId)}`, {
        method: 'PATCH',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({
            enabled: false,
            levels_mode: 'off',
            black_percentile: 0,
            white_percentile: 100,
            gamma_mode: 'off',
            gamma: 1,
            denoise_mode: 'off',
            denoise_radius: 0,
            sharpen_mode: 'off',
            sharpen: 0,
            edge_mode: 'off',
            edge_strength: 1,
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
