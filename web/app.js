// app.js

document.addEventListener('DOMContentLoaded', () => {
    // State management
    const state = {
        mode: 'music',
        color: '#00ff88',
        speed: 2,
        gain: 1.5,
        device: { name: 'Detecting...', path: '' }
    };

    // DOM Elements
    const deviceNameEl = document.getElementById('device-name');
    const colorPicker = document.getElementById('color-picker');
    const colorHex = document.getElementById('color-hex');
    const colorRgb = document.getElementById('color-rgb');
    const colorSwatch = document.getElementById('color-swatch');
    const speedSlider = document.getElementById('speed-slider');
    const speedVal = document.getElementById('speed-val');
    const gainSlider = document.getElementById('gain-slider');
    const gainVal = document.getElementById('gain-val');
    const beatBar = document.getElementById('beat-bar');
    const visualizerOffOverlay = document.getElementById('visualizer-off-overlay');
    const colorPickerGroup = document.getElementById('color-picker-group');

    // Mode Buttons
    const modeButtons = document.querySelectorAll('.mode-btn');

    // Canvas configuration
    const canvas = document.getElementById('visualizer-canvas');
    const ctx = canvas.getContext('2d');
    
    // Resize canvas on start
    function resizeCanvas() {
        canvas.width = canvas.parentElement.clientWidth * window.devicePixelRatio;
        canvas.height = canvas.parentElement.clientHeight * window.devicePixelRatio;
        ctx.scale(window.devicePixelRatio, window.devicePixelRatio);
    }
    resizeCanvas();
    window.addEventListener('resize', resizeCanvas);

    // Speed slider label mapping
    const speedLabels = {
        0: '0 (Fastest)',
        1: '1 (Fast)',
        2: '2 (Medium)',
        3: '3 (Slow)',
        4: '4 (Slowest)'
    };

    // Helper: hex to RGB object
    function hexToRgb(hex) {
        const result = /^#?([a-f\d]{2})([a-f\d]{2})([a-f\d]{2})$/i.exec(hex);
        return result ? {
            r: parseInt(result[1], 16),
            g: parseInt(result[2], 16),
            b: parseInt(result[3], 16)
        } : { r: 0, g: 255, b: 136 };
    }

    // Helper: RGB object to string
    function rgbToString(rgb) {
        return `RGB: ${rgb.r}, ${rgb.g}, ${rgb.b}`;
    }

    // Send control update to backend
    async function updateControl() {
        const rgb = hexToRgb(state.color);
        const body = {
            mode: state.mode,
            r: rgb.r,
            g: rgb.g,
            b: rgb.b,
            speed: parseInt(state.speed),
            gain: parseFloat(state.gain)
        };

        try {
            const res = await fetch('/api/control', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(body)
            });
            if (!res.ok) {
                console.error('Failed to update settings');
            }
        } catch (err) {
            console.error('API Error:', err);
        }
    }

    // Event Listeners for controls
    modeButtons.forEach(btn => {
        btn.addEventListener('click', () => {
            modeButtons.forEach(b => b.classList.remove('active'));
            btn.classList.add('active');
            state.mode = btn.getAttribute('data-mode');

            // Handle conditional UI display
            if (state.mode === 'static' || state.mode === 'breathing' || state.mode === 'ripple' || state.mode === 'reactive' || state.mode === 'starlight') {
                colorPickerGroup.style.display = 'block';
            } else {
                colorPickerGroup.style.display = 'none';
            }

            if (state.mode === 'music') {
                visualizerOffOverlay.classList.remove('active');
            } else {
                visualizerOffOverlay.classList.add('active');
                beatBar.style.width = '0%';
            }

            updateControl();
        });
    });

    colorPicker.addEventListener('input', (e) => {
        state.color = e.target.value;
        colorHex.textContent = state.color.toUpperCase();
        const rgb = hexToRgb(state.color);
        colorRgb.textContent = rgbToString(rgb);
        colorSwatch.style.backgroundColor = state.color;
        colorSwatch.style.boxShadow = `0 0 12px ${state.color}a0`;
        updateControl();
    });

    speedSlider.addEventListener('input', (e) => {
        state.speed = e.target.value;
        speedVal.textContent = speedLabels[state.speed];
        updateControl();
    });

    gainSlider.addEventListener('input', (e) => {
        state.gain = e.target.value;
        gainVal.textContent = `${state.gain}x`;
        updateControl();
    });

    // Audio Visualizer drawing logic
    let audioHistory = [];
    const maxHistory = 100;

    function drawVisualizer(samples, volume, colorHex) {
        const w = canvas.width / window.devicePixelRatio;
        const h = canvas.height / window.devicePixelRatio;
        
        // Clear canvas
        ctx.fillStyle = '#06080d';
        ctx.fillRect(0, 0, w, h);

        if (state.mode !== 'music') return;

        // Draw background grid
        ctx.strokeStyle = 'rgba(255, 255, 255, 0.02)';
        ctx.lineWidth = 1;
        for (let i = 0; i < w; i += 30) {
            ctx.beginPath();
            ctx.moveTo(i, 0);
            ctx.lineTo(i, h);
            ctx.stroke();
        }
        for (let i = 0; i < h; i += 30) {
            ctx.beginPath();
            ctx.moveTo(0, i);
            ctx.lineTo(w, i);
            ctx.stroke();
        }

        // Draw waveform path
        if (samples && samples.length > 0) {
            ctx.strokeStyle = colorHex;
            ctx.shadowBlur = 15;
            ctx.shadowColor = colorHex;
            ctx.lineWidth = 3;
            ctx.beginPath();

            const step = w / samples.length;
            for (let i = 0; i < samples.length; i++) {
                // Map samples (-32768 to 32767) to canvas height
                const val = (samples[i] / 32768) * (h / 2.2) * state.gain;
                const x = i * step;
                const y = (h / 2) + val;

                if (i === 0) {
                    ctx.moveTo(x, y);
                } else {
                    ctx.lineTo(x, y);
                }
            }
            ctx.stroke();
            ctx.shadowBlur = 0; // reset
        }

        // Draw central dynamic pulse ring/circle in background
        ctx.fillStyle = 'rgba(0,0,0,0)';
        ctx.strokeStyle = 'rgba(255, 255, 255, 0.05)';
        ctx.lineWidth = 1;
        ctx.beginPath();
        ctx.arc(w / 2, h / 2, 40 + volume * 30, 0, Math.PI * 2);
        ctx.stroke();
    }

    // Connect to Server-Sent Events stream
    function connectSSE() {
        console.log('[*] Connecting to event stream...');
        const source = new EventSource('/api/stream');

        source.onmessage = (event) => {
            try {
                const data = JSON.parse(event.data);

                // Handle system device detection event
                if (data.type === 'device') {
                    state.device = data.device;
                    deviceNameEl.textContent = state.device.name;
                    deviceNameEl.parentElement.classList.add('active');
                }

                // Handle audio volume & waveform event
                if (data.type === 'audio' && state.mode === 'music') {
                    const volume = data.volume; // 0.0 to 1.0
                    const samples = data.samples; // list of ints
                    const currentRgb = data.color; // {r, g, b}
                    
                    // Convert RGB object to hex string
                    const hex = "#" + ((1 << 24) + (currentRgb.r << 16) + (currentRgb.g << 8) + currentRgb.b).toString(16).slice(1);
                    
                    // Update beat bar
                    beatBar.style.width = `${volume * 100}%`;
                    colorSwatch.style.backgroundColor = hex;
                    colorSwatch.style.boxShadow = `0 0 12px ${hex}a0`;

                    // Render wave
                    drawVisualizer(samples, volume, hex);
                }

                // Handle state updates from backend (e.g. initially loaded values)
                if (data.type === 'state') {
                    state.mode = data.state.mode;
                    state.gain = data.state.gain;
                    state.speed = data.state.speed;
                    
                    // Update active button state
                    modeButtons.forEach(btn => {
                        if (btn.getAttribute('data-mode') === state.mode) {
                            btn.classList.add('active');
                        } else {
                            btn.classList.remove('active');
                        }
                    });

                    if (state.mode === 'music') {
                        visualizerOffOverlay.classList.remove('active');
                    } else {
                        visualizerOffOverlay.classList.add('active');
                    }

                    gainSlider.value = state.gain;
                    gainVal.textContent = `${state.gain}x`;
                    speedSlider.value = state.speed;
                    speedVal.textContent = speedLabels[state.speed];
                }
            } catch (err) {
                console.error('Error parsing SSE event:', err);
            }
        };

        source.onerror = (err) => {
            console.error('[!] Event stream disconnected. Reconnecting in 3s...', err);
            source.close();
            setTimeout(connectSSE, 3000);
        };
    }

    connectSSE();
});
