let cameras = [];
let selectedCameraId = null;
let latestSample = null;
let peakScore = 0;
let history = [];
let lastFrameNumber = null;
let sampleBusy = false;
let roi = {x: 0.5, y: 0.5, size: 0.25};

const cameraSelect = document.getElementById('focus-camera');
const focusImage = document.getElementById('focus-image');
const focusStage = document.getElementById('focus-stage');
const overlay = document.getElementById('roi-overlay');
const roiPreview = document.getElementById('roi-preview');
const chart = document.getElementById('focus-chart');

async function api(path, options = {}) {
    const response = await fetch(path, options);
    const data = await response.json();

    if (!response.ok) {
        throw new Error(data.error || `Request failed: ${response.status}`);
    }

    return data;
}

function showMessage(text, isError = false) {
    const message = document.getElementById('message');
    message.textContent = text;
    message.classList.toggle('error', isError);
}

function cameraLabel(camera) {
    const name = camera.model
        ? `${camera.name} — ${camera.model}`
        : camera.name;
    return `${name} [${camera.backend}]`;
}

function currentCamera() {
    return cameras.find(camera => camera.id === selectedCameraId);
}

function resetTracking(message = 'Peak and trend reset.') {
    peakScore = 0;
    history = [];
    lastFrameNumber = null;
    latestSample = null;
    document.getElementById('focus-score').textContent = '—';
    document.getElementById('peak-score').textContent = '—';
    document.getElementById('peak-percent').textContent = '—';
    document.getElementById('laplacian-score').textContent = '—';
    document.getElementById('contrast-score').textContent = '—';
    document.getElementById('focus-meter').style.width = '0';
    drawChart();
    showMessage(message);
}

function selectCamera(cameraId) {
    if (!cameraId || cameraId === selectedCameraId) {
        return;
    }

    selectedCameraId = cameraId;
    cameraSelect.value = cameraId;
    focusImage.src = `/focus/stream/${encodeURIComponent(cameraId)}?t=${Date.now()}`;
    renderFocusControls();
    resetTracking('Camera selected. Click the image to place the focus ROI.');
}

async function refreshCameras() {
    try {
        const data = await api('/api/focus/cameras');
        cameras = data.cameras;
        const prior = selectedCameraId;
        cameraSelect.replaceChildren();

        for (const camera of cameras) {
            const option = document.createElement('option');
            option.value = camera.id;
            option.textContent = cameraLabel(camera);
            option.disabled = !camera.running || !camera.has_frame;
            cameraSelect.append(option);
        }

        const selectedIsAvailable = cameras.some(camera => (
            camera.id === prior && camera.running && camera.has_frame
        ));
        const fallback = cameras.find(camera => camera.running && camera.has_frame);

        if (!selectedIsAvailable && fallback) {
            selectedCameraId = null;
            selectCamera(fallback.id);
        } else if (selectedIsAvailable) {
            cameraSelect.value = prior;
        } else if (selectedCameraId !== null) {
            selectedCameraId = null;
            focusImage.removeAttribute('src');
            renderFocusControls();
            resetTracking('No streaming camera is currently available.');
        }

        const camera = currentCamera();
        document.getElementById('camera-status').textContent = camera
            ? (camera.last_error || (camera.running ? 'Streaming' : 'Stopped'))
            : 'No streaming camera';
        cameraSelect.disabled = !fallback;
    } catch (error) {
        showMessage(error.message, true);
    }
}

function capability(id) {
    return currentCamera()?.focus_capabilities.find(item => item.id === id);
}

function renderFocusControls() {
    const container = document.getElementById('focus-controls');
    const mode = capability('focus_mode');
    const position = capability('focus_position');
    container.replaceChildren();

    if (!mode && !position) {
        container.textContent = (
            'No electronic focus controls reported. Use the live metric while ' +
            'adjusting the lens mechanically.'
        );
        return;
    }

    if (mode) {
        const buttons = document.createElement('div');
        buttons.className = 'focus-buttons';

        for (const [label, value] of [
            ['Auto once', 'single'],
            ['Continuous AF', 'continuous'],
            ['Manual', 'manual']
        ]) {
            const button = document.createElement('button');
            button.textContent = label;
            button.addEventListener('click', () => setFocusControl(
                'focus_mode',
                value,
                value === 'single' ? 'Autofocus scan started.' : `${label} selected.`
            ));
            buttons.append(button);
        }

        container.append(buttons);
    }

    if (position) {
        const row = document.createElement('div');
        row.className = 'lens-position-row';
        const label = document.createElement('span');
        label.textContent = 'Lens position';
        const slider = document.createElement('input');
        slider.id = 'lens-position';
        slider.type = 'range';
        slider.min = position.minimum ?? 0;
        slider.max = position.maximum ?? 32;
        slider.step = position.step ?? 0.05;
        slider.value = position.value ?? slider.min;
        const output = document.createElement('output');
        output.id = 'lens-position-value';
        output.textContent = Number(slider.value).toFixed(2);
        slider.addEventListener('input', () => {
            output.textContent = Number(slider.value).toFixed(2);
        });
        slider.addEventListener('change', () => setFocusControl(
            'focus_position',
            Number(slider.value),
            `Manual lens position set to ${Number(slider.value).toFixed(2)}.`
        ));
        row.append(label, slider, output);
        container.append(row);
    }
}

async function setFocusControl(controlId, value, message) {
    if (!selectedCameraId) {
        return;
    }

    try {
        await api(
            `/api/focus/${encodeURIComponent(selectedCameraId)}/control`,
            {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({control_id: controlId, value})
            }
        );
        resetTracking(message);
    } catch (error) {
        showMessage(error.message, true);
    }
}

function metricUrl() {
    const params = new URLSearchParams({
        x: roi.x.toFixed(6),
        y: roi.y.toFixed(6),
        size: roi.size.toFixed(3)
    });
    return `/api/focus/${encodeURIComponent(selectedCameraId)}/metrics?${params}`;
}

async function sampleFocus() {
    if (!selectedCameraId || sampleBusy) {
        return;
    }

    sampleBusy = true;

    try {
        const sample = await api(metricUrl());
        latestSample = sample;

        if (sample.frame_number !== lastFrameNumber) {
            lastFrameNumber = sample.frame_number;
            peakScore = Math.max(peakScore, sample.tenengrad);
            history.push(sample.tenengrad);

            if (history.length > 120) {
                history.shift();
            }
        }

        renderMetrics(sample);
        drawRoiOverlay();
        drawRoiPreview();
        drawChart();
    } catch (error) {
        showMessage(error.message, true);
    } finally {
        sampleBusy = false;
    }
}

function scoreText(value) {
    return Number.isFinite(value) ? value.toFixed(3) : '—';
}

function renderMetrics(sample) {
    const percent = peakScore > 0
        ? Math.min(100, sample.tenengrad * 100 / peakScore)
        : 0;
    document.getElementById('focus-score').textContent = scoreText(sample.tenengrad);
    document.getElementById('peak-score').textContent = scoreText(peakScore);
    document.getElementById('peak-percent').textContent = `${percent.toFixed(0)}%`;
    document.getElementById('laplacian-score').textContent = scoreText(sample.laplacian);
    document.getElementById('contrast-score').textContent = scoreText(sample.contrast);
    document.getElementById('focus-meter').style.width = `${percent}%`;

    const states = ['Idle', 'Scanning', 'Focused', 'Failed'];
    const state = sample.autofocus_state;
    const parts = [];

    if (state !== null && state !== undefined) {
        parts.push(`AF: ${states[state] || state}`);
    }
    if (sample.lens_position !== null && sample.lens_position !== undefined) {
        parts.push(`Lens: ${Number(sample.lens_position).toFixed(2)}`);
        const slider = document.getElementById('lens-position');
        const output = document.getElementById('lens-position-value');

        if (slider && document.activeElement !== slider) {
            slider.value = sample.lens_position;
            output.textContent = Number(sample.lens_position).toFixed(2);
        }
    }

    document.getElementById('autofocus-status').textContent = parts.join(' | ');
}

function sizeCanvas(canvas) {
    const ratio = window.devicePixelRatio || 1;
    const width = Math.max(1, Math.round(canvas.clientWidth * ratio));
    const height = Math.max(1, Math.round(canvas.clientHeight * ratio));

    if (canvas.width !== width || canvas.height !== height) {
        canvas.width = width;
        canvas.height = height;
    }

    return {width, height};
}

function displayedImageRect() {
    if (!focusImage.naturalWidth || !focusImage.naturalHeight) {
        return null;
    }

    const stage = focusStage.getBoundingClientRect();
    const imageAspect = focusImage.naturalWidth / focusImage.naturalHeight;
    const stageAspect = stage.width / stage.height;
    let width;
    let height;

    if (imageAspect > stageAspect) {
        width = stage.width;
        height = width / imageAspect;
    } else {
        height = stage.height;
        width = height * imageAspect;
    }

    return {
        left: (stage.width - width) / 2,
        top: (stage.height - height) / 2,
        width,
        height,
        stage
    };
}

function drawRoiOverlay() {
    const dimensions = sizeCanvas(overlay);
    const context = overlay.getContext('2d');
    context.clearRect(0, 0, dimensions.width, dimensions.height);

    if (!latestSample) {
        return;
    }

    const displayed = displayedImageRect();

    if (!displayed) {
        return;
    }

    const ratio = window.devicePixelRatio || 1;
    const [x0, y0, x1, y1] = latestSample.roi;
    const x = displayed.left + x0 * displayed.width / latestSample.width;
    const y = displayed.top + y0 * displayed.height / latestSample.height;
    const width = (x1 - x0) * displayed.width / latestSample.width;
    const height = (y1 - y0) * displayed.height / latestSample.height;
    context.strokeStyle = '#ffeb3b';
    context.lineWidth = 2 * ratio;
    context.strokeRect(x * ratio, y * ratio, width * ratio, height * ratio);
    context.beginPath();
    context.moveTo((x + width / 2 - 8) * ratio, (y + height / 2) * ratio);
    context.lineTo((x + width / 2 + 8) * ratio, (y + height / 2) * ratio);
    context.moveTo((x + width / 2) * ratio, (y + height / 2 - 8) * ratio);
    context.lineTo((x + width / 2) * ratio, (y + height / 2 + 8) * ratio);
    context.stroke();
}

function drawRoiPreview() {
    const dimensions = sizeCanvas(roiPreview);
    const context = roiPreview.getContext('2d', {willReadFrequently: true});
    context.clearRect(0, 0, dimensions.width, dimensions.height);

    if (!latestSample || !focusImage.naturalWidth) {
        return;
    }

    const [x0, y0, x1, y1] = latestSample.roi;
    context.drawImage(
        focusImage,
        x0, y0, x1 - x0, y1 - y0,
        0, 0, dimensions.width, dimensions.height
    );

    if (document.getElementById('roi-view').value === 'edges') {
        renderEdges(context, dimensions.width, dimensions.height);
    }
}

function renderEdges(context, width, height) {
    const image = context.getImageData(0, 0, width, height);
    const source = new Uint8ClampedArray(image.data);

    for (let y = 1; y < height - 1; y += 1) {
        for (let x = 1; x < width - 1; x += 1) {
            const index = (y * width + x) * 4;
            const left = source[index - 4];
            const right = source[index + 4];
            const above = source[index - width * 4];
            const below = source[index + width * 4];
            const magnitude = Math.min(255, Math.abs(right - left) + Math.abs(below - above));
            image.data[index] = magnitude;
            image.data[index + 1] = magnitude;
            image.data[index + 2] = magnitude;
            image.data[index + 3] = 255;
        }
    }

    context.putImageData(image, 0, 0);
}

function drawChart() {
    const dimensions = sizeCanvas(chart);
    const context = chart.getContext('2d');
    context.fillStyle = '#101010';
    context.fillRect(0, 0, dimensions.width, dimensions.height);

    if (history.length < 2) {
        return;
    }

    const maximum = Math.max(...history, 1e-9);
    const minimum = Math.min(...history);
    const span = Math.max(maximum - minimum, maximum * 0.05, 1e-9);
    context.strokeStyle = '#66bb6a';
    context.lineWidth = 2 * (window.devicePixelRatio || 1);
    context.beginPath();

    history.forEach((value, index) => {
        const x = index * dimensions.width / Math.max(1, history.length - 1);
        const y = dimensions.height - (
            (value - minimum) / span * (dimensions.height - 8)
        ) - 4;

        if (index === 0) {
            context.moveTo(x, y);
        } else {
            context.lineTo(x, y);
        }
    });
    context.stroke();
}

focusStage.addEventListener('click', event => {
    const displayed = displayedImageRect();

    if (!displayed) {
        return;
    }

    const x = event.clientX - displayed.stage.left - displayed.left;
    const y = event.clientY - displayed.stage.top - displayed.top;

    if (x < 0 || y < 0 || x >= displayed.width || y >= displayed.height) {
        return;
    }

    roi.x = x / displayed.width;
    roi.y = y / displayed.height;
    resetTracking('Focus ROI moved; peak and trend reset.');
    sampleFocus();
});

cameraSelect.addEventListener('change', event => selectCamera(event.target.value));

document.getElementById('roi-size').addEventListener('change', event => {
    roi.size = Number(event.target.value);
    resetTracking('ROI size changed; peak and trend reset.');
    sampleFocus();
});

document.getElementById('roi-view').addEventListener('change', drawRoiPreview);
document.getElementById('reset-peak').addEventListener('click', () => resetTracking());
window.addEventListener('resize', () => {
    drawRoiOverlay();
    drawRoiPreview();
    drawChart();
});

refreshCameras();
setInterval(refreshCameras, 2000);
setInterval(sampleFocus, 125);
