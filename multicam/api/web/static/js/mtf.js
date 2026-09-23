const camera = document.getElementById('camera');
const frame = document.getElementById('frame');
const stage = document.getElementById('stage');
const selection = document.getElementById('selection');
const analyze = document.getElementById('analyze');
const statusLine = document.getElementById('status');
let roi = null;
let start = null;

async function api(url, options) {
    const response = await fetch(url, options);
    const data = await response.json();
    if (!response.ok) throw new Error(data.error || 'Request failed');
    return data;
}

function status(message, error = false) {
    statusLine.textContent = message;
    statusLine.style.color = error ? '#ff8d8d' : '#78c9ff';
}

async function loadCameras() {
    const data = await api('/api/mtf/cameras');
    camera.replaceChildren();
    data.cameras.filter(item => item.running && item.has_frame).forEach(item => {
        const option = document.createElement('option');
        option.value = item.id;
        option.textContent = `${item.name} — ${item.backend}`;
        camera.appendChild(option);
    });
    if (!camera.value) status('No running cameras with frames.', true);
}

document.getElementById('freeze').addEventListener('click', async () => {
    try {
        const result = await api('/api/mtf/freeze', {
            method: 'POST', headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({camera_id: camera.value})
        });
        roi = null; selection.style.display = 'none'; analyze.disabled = true;
        frame.src = `/api/mtf/frame/${encodeURIComponent(camera.value)}?t=${Date.now()}`;
        status(`Frozen ${result.width} × ${result.height} raw frame. Drag an ROI.`);
    } catch (error) { status(error.message, true); }
});

stage.addEventListener('pointerdown', event => {
    if (!frame.src) return;
    const rect = frame.getBoundingClientRect();
    start = {x: event.clientX - rect.left, y: event.clientY - rect.top};
    stage.setPointerCapture(event.pointerId);
});

stage.addEventListener('pointermove', event => {
    if (!start) return;
    const rect = frame.getBoundingClientRect();
    const end = {x: event.clientX - rect.left, y: event.clientY - rect.top};
    const left = Math.max(0, Math.min(start.x, end.x));
    const top = Math.max(0, Math.min(start.y, end.y));
    const width = Math.min(rect.width, Math.max(start.x, end.x)) - left;
    const height = Math.min(rect.height, Math.max(start.y, end.y)) - top;
    Object.assign(selection.style, {display: 'block', left: `${left}px`, top: `${top}px`, width: `${width}px`, height: `${height}px`});
});

stage.addEventListener('pointerup', event => {
    if (!start) return;
    const rect = frame.getBoundingClientRect();
    const clamp = (value, maximum) => Math.max(0, Math.min(maximum, value));
    const end = {
        x: clamp(event.clientX - rect.left, rect.width),
        y: clamp(event.clientY - rect.top, rect.height)
    };
    roi = [
        clamp(start.x, rect.width) / rect.width,
        clamp(start.y, rect.height) / rect.height,
        end.x / rect.width,
        end.y / rect.height
    ];
    start = null; analyze.disabled = false; status('ROI selected. Choose analysis and click Analyze ROI.');
});

function metric(label, value) {
    return `<div class="metric">${label}<strong>${value}</strong></div>`;
}

function frequency(value) {
    return value === null || value === undefined
        ? 'No crossing'
        : `${value.toFixed(4)} cy/px`;
}

function drawCurve(x, y, label) {
    const canvas = document.getElementById('curve');
    const ctx = canvas.getContext('2d');
    ctx.clearRect(0, 0, canvas.width, canvas.height);
    ctx.fillStyle = '#fff'; ctx.fillRect(0, 0, canvas.width, canvas.height);
    if (!x || !y || x.length < 2) return;
    const pad = 45, width = canvas.width - 2 * pad, height = canvas.height - 2 * pad;
    const ymin = Math.min(...y), ymax = Math.max(...y);
    ctx.strokeStyle = '#222'; ctx.strokeRect(pad, pad, width, height);
    ctx.strokeStyle = '#087ec1'; ctx.lineWidth = 2; ctx.beginPath();
    y.forEach((value, index) => {
        const px = pad + width * index / (y.length - 1);
        const py = pad + height * (1 - (value - ymin) / Math.max(1e-9, ymax - ymin));
        index ? ctx.lineTo(px, py) : ctx.moveTo(px, py);
    });
    ctx.stroke(); ctx.fillStyle = '#111'; ctx.font = '16px Arial'; ctx.fillText(label, pad, 25);
}

analyze.addEventListener('click', async () => {
    try {
        const result = await api('/api/mtf/analyze', {
            method: 'POST', headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({camera_id: camera.value, mode: document.getElementById('mode').value, roi})
        });
        if (result.mode === 'slanted_edge') {
            document.getElementById('metrics').innerHTML =
                metric('MTF50', frequency(result.mtf50_cycles_per_pixel)) +
                metric('MTF20', frequency(result.mtf20_cycles_per_pixel)) +
                metric('MTF10', frequency(result.mtf10_cycles_per_pixel)) +
                metric('Edge slant', result.slant_degrees.toFixed(2) + '°') +
                metric('Contrast', result.contrast.toFixed(1)) +
                metric('Valid', result.valid ? 'Yes' : 'Review');
            drawCurve(result.frequency_cycles_per_pixel, result.mtf, 'Normalized MTF');
            status(result.warning || 'Slanted-edge measurement complete.', Boolean(result.warning));
        } else {
            document.getElementById('metrics').innerHTML =
                metric('Bar modulation', (100 * result.modulation).toFixed(1) + '%') +
                metric('Dominant frequency', result.dominant_frequency_cycles_per_pixel.toFixed(4) + ' cy/px') +
                metric('Orientation', result.orientation) + metric('Valid', result.valid ? 'Yes' : 'Review');
            drawCurve(result.profile.map((_, i) => i), result.profile, 'Mean bar profile');
            status('USAF / tri-bar measurement complete.');
        }
    } catch (error) { status(error.message, true); }
});

loadCameras().catch(error => status(error.message, true));
