#!/usr/bin/env python3
"""Browser-based GUI for converting JPG/JPEG to WebP/AVIF in parallel."""

from __future__ import annotations

import io
import secrets
import threading
import zipfile
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any

from flask import Flask, Response, jsonify, render_template_string, request
from PIL import Image

app = Flask(__name__)

JOBS: dict[str, dict[str, Any]] = {}
JOBS_LOCK = threading.Lock()

HTML = """
<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>JPG/JPEG to WebP/AVIF</title>
  <style>
    :root {
      --bg: #0f172a;
      --card: #111827;
      --muted: #94a3b8;
      --text: #e2e8f0;
      --accent: #22c55e;
      --accent-2: #0ea5e9;
      --danger: #ef4444;
      --line: #1f2937;
      --ok: #34d399;
    }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      font-family: "SF Pro Text", "Segoe UI", -apple-system, sans-serif;
      color: var(--text);
      background:
        radial-gradient(1200px 600px at 10% -10%, #1e293b 0%, transparent 60%),
        radial-gradient(1200px 700px at 100% 0%, #0c4a6e 0%, transparent 55%),
        var(--bg);
      min-height: 100vh;
      display: grid;
      place-items: center;
      padding: 24px;
    }
    .card {
      width: min(760px, 100%);
      background: color-mix(in srgb, var(--card) 92%, black);
      border: 1px solid var(--line);
      border-radius: 16px;
      padding: 20px;
      box-shadow: 0 20px 50px rgba(0, 0, 0, 0.35);
    }
    h1 { margin: 0 0 8px; font-size: 1.5rem; }
    p { margin: 0 0 16px; color: var(--muted); }
    .grid {
      display: grid;
      grid-template-columns: repeat(2, minmax(0, 1fr));
      gap: 12px;
    }
    @media (max-width: 700px) { .grid { grid-template-columns: 1fr; } }
    label { display: block; margin-bottom: 6px; font-weight: 600; }
    input, select, button {
      width: 100%;
      border-radius: 10px;
      border: 1px solid var(--line);
      background: #0b1220;
      color: var(--text);
      padding: 10px 12px;
      font-size: 0.95rem;
    }
    input[type="file"] { padding: 10px; }
    button {
      border: none;
      background: linear-gradient(90deg, var(--accent), var(--accent-2));
      color: #041014;
      font-weight: 700;
      cursor: pointer;
      margin-top: 10px;
    }
    button:disabled {
      opacity: 0.55;
      cursor: not-allowed;
    }
    .dropzone {
      margin-top: 10px;
      border: 1px dashed #334155;
      border-radius: 12px;
      padding: 14px;
      text-align: center;
      color: var(--muted);
      transition: border-color 0.2s ease, background-color 0.2s ease;
    }
    .dropzone.active {
      border-color: var(--accent-2);
      background: rgba(14, 165, 233, 0.12);
      color: var(--text);
    }
    .meta { margin-top: 8px; color: var(--muted); font-size: 0.9rem; }
    .progress-wrap {
      margin-top: 14px;
      border: 1px solid var(--line);
      border-radius: 12px;
      padding: 10px;
      background: #0b1220;
    }
    .bar {
      width: 100%;
      height: 12px;
      border-radius: 999px;
      background: #1e293b;
      overflow: hidden;
      border: 1px solid #263447;
    }
    .bar-fill {
      height: 100%;
      width: 0%;
      background: linear-gradient(90deg, var(--accent), var(--accent-2));
      transition: width 0.2s ease;
    }
    .status {
      margin-top: 8px;
      font-size: 0.92rem;
      color: var(--muted);
    }
    .success {
      margin-top: 10px;
      color: var(--ok);
      font-weight: 600;
    }
    .error {
      margin-top: 12px;
      padding: 10px 12px;
      border: 1px solid color-mix(in srgb, var(--danger) 65%, black);
      border-radius: 10px;
      background: rgba(239, 68, 68, 0.1);
      color: #fecaca;
    }
  </style>
</head>
<body>
  <main class="card">
    <h1>JPG/JPEG to WebP/AVIF Converter</h1>
    <p>Upload many images, pick one format, and download one ZIP file.</p>

    <form id="convertForm">
      <div>
        <label for="files">Images (.jpg/.jpeg)</label>
        <input id="files" name="files" type="file" multiple accept=".jpg,.jpeg,.JPG,.JPEG" required />
        <div id="dropzone" class="dropzone">Drag and drop JPG/JPEG files here</div>
        <div id="fileMeta" class="meta">No files selected</div>
      </div>

      <div class="grid" style="margin-top: 12px;">
        <div>
          <label for="format">Format</label>
          <select id="format" name="format" required>
            <option value="webp" selected>WebP</option>
            <option value="avif">AVIF</option>
          </select>
        </div>

        <div>
          <label for="quality">Quality (1-100)</label>
          <input id="quality" name="quality" type="number" min="1" max="100" value="80" />
        </div>

        <div>
          <label for="workers">Parallel jobs (1-32)</label>
          <input id="workers" name="workers" type="number" min="1" max="32" value="12" />
        </div>
      </div>

      <button id="submitBtn" type="submit">Convert</button>
      <div class="meta">Recommended for 117 images: 8-16 parallel jobs.</div>

      <div class="progress-wrap">
        <div class="bar"><div id="barFill" class="bar-fill"></div></div>
        <div id="statusText" class="status">Idle</div>
      </div>

      <div id="successText" class="success" style="display:none;"></div>
      <div id="errorText" class="error" style="display:none;"></div>
    </form>
  </main>

  <script>
    const form = document.getElementById('convertForm');
    const fileInput = document.getElementById('files');
    const dropzone = document.getElementById('dropzone');
    const fileMeta = document.getElementById('fileMeta');
    const submitBtn = document.getElementById('submitBtn');
    const barFill = document.getElementById('barFill');
    const statusText = document.getElementById('statusText');
    const successText = document.getElementById('successText');
    const errorText = document.getElementById('errorText');

    function setError(msg) {
      errorText.textContent = msg;
      errorText.style.display = 'block';
    }

    function clearMessages() {
      errorText.style.display = 'none';
      errorText.textContent = '';
      successText.style.display = 'none';
      successText.textContent = '';
    }

    function updateFileMeta() {
      const count = fileInput.files.length;
      fileMeta.textContent = count > 0 ? `${count} file(s) selected` : 'No files selected';
    }

    fileInput.addEventListener('change', updateFileMeta);

    ['dragenter', 'dragover'].forEach(evt => {
      dropzone.addEventListener(evt, (e) => {
        e.preventDefault();
        e.stopPropagation();
        dropzone.classList.add('active');
      });
    });

    ['dragleave', 'drop'].forEach(evt => {
      dropzone.addEventListener(evt, (e) => {
        e.preventDefault();
        e.stopPropagation();
        dropzone.classList.remove('active');
      });
    });

    dropzone.addEventListener('drop', (e) => {
      const incoming = e.dataTransfer.files;
      const dt = new DataTransfer();
      for (const file of incoming) {
        const name = file.name.toLowerCase();
        if (name.endsWith('.jpg') || name.endsWith('.jpeg')) {
          dt.items.add(file);
        }
      }
      fileInput.files = dt.files;
      updateFileMeta();
    });

    async function pollStatus(jobId) {
      while (true) {
        const res = await fetch(`/status/${jobId}`);
        if (!res.ok) {
          throw new Error('Status check failed.');
        }
        const data = await res.json();
        const pct = data.total > 0 ? Math.round((data.completed / data.total) * 100) : 0;
        barFill.style.width = `${pct}%`;
        statusText.textContent = `${data.state}: ${data.completed}/${data.total} (${pct}%)`;

        if (data.state === 'done') {
          successText.style.display = 'block';
          successText.innerHTML = `Conversion complete. <a href="/download/${jobId}" style="color:#86efac;">Download ZIP</a>`;
          return;
        }

        if (data.state === 'error') {
          throw new Error(data.error || 'Conversion failed.');
        }

        await new Promise(r => setTimeout(r, 350));
      }
    }

    form.addEventListener('submit', async (e) => {
      e.preventDefault();
      clearMessages();

      if (fileInput.files.length === 0) {
        setError('Please select at least one JPG/JPEG file.');
        return;
      }

      submitBtn.disabled = true;
      barFill.style.width = '0%';
      statusText.textContent = 'Starting...';

      try {
        const formData = new FormData(form);
        const res = await fetch('/start', { method: 'POST', body: formData });
        const data = await res.json();

        if (!res.ok) {
          throw new Error(data.error || 'Failed to start conversion.');
        }

        await pollStatus(data.job_id);
      } catch (err) {
        setError(err.message || 'Something went wrong.');
      } finally {
        submitBtn.disabled = false;
      }
    });
  </script>
</body>
</html>
"""


def avif_available() -> bool:
    try:
        buf = io.BytesIO()
        Image.new("RGB", (1, 1), color=(0, 0, 0)).save(buf, format="AVIF")
        return True
    except Exception:
        return False


def convert_one(raw: bytes, filename: str, fmt: str, quality: int) -> tuple[str, bytes]:
    stem = Path(filename).stem
    out_name = f"{stem}.webp" if fmt == "webp" else f"{stem}.avif"

    with Image.open(io.BytesIO(raw)) as im:
        out = io.BytesIO()
        im.convert("RGB").save(out, format=fmt.upper(), quality=quality)
        return out_name, out.getvalue()


def set_job(job_id: str, **kwargs: Any) -> None:
    with JOBS_LOCK:
        job = JOBS.get(job_id)
        if not job:
            return
        job.update(kwargs)


def run_job(job_id: str, payloads: list[tuple[str, bytes]], fmt: str, quality: int, workers: int) -> None:
    try:
        results: list[tuple[str, bytes]] = []
        name_counts: dict[str, int] = {}

        # Chunking keeps large batches stable by limiting futures in-flight.
        chunk_size = 24
        tasks = [(name, raw, fmt) for name, raw in payloads]

        completed = 0
        total = len(tasks)
        set_job(job_id, state="running", completed=0, total=total)

        for idx in range(0, total, chunk_size):
            chunk = tasks[idx : idx + chunk_size]
            with ThreadPoolExecutor(max_workers=workers) as pool:
                futures = [pool.submit(convert_one, raw, name, one_fmt, quality) for name, raw, one_fmt in chunk]
                for fut in as_completed(futures):
                    out_name, out_data = fut.result()

                    if out_name in name_counts:
                        name_counts[out_name] += 1
                        stem = Path(out_name).stem
                        ext = Path(out_name).suffix
                        safe_name = f"{stem}_{name_counts[out_name]}{ext}"
                    else:
                        name_counts[out_name] = 1
                        safe_name = out_name

                    results.append((safe_name, out_data))
                    completed += 1
                    set_job(job_id, completed=completed)

        zip_buf = io.BytesIO()
        with zipfile.ZipFile(zip_buf, mode="w", compression=zipfile.ZIP_DEFLATED) as zf:
            for out_name, out_data in sorted(results):
                zf.writestr(out_name, out_data)

        zip_buf.seek(0)
        set_job(job_id, state="done", zip_bytes=zip_buf.getvalue(), completed=total)
    except Exception as err:
        set_job(job_id, state="error", error=str(err))


@app.route("/", methods=["GET"])
def index() -> str:
    return render_template_string(HTML)


@app.route("/start", methods=["POST"])
def start() -> tuple[Response, int] | Response:
    files = request.files.getlist("files")
    if not files:
        return jsonify({"error": "Please upload at least one image."}), 400

    fmt = request.form.get("format", "webp")
    if fmt not in {"webp", "avif"}:
        return jsonify({"error": "Invalid format selected."}), 400

    if fmt == "avif" and not avif_available():
        return jsonify({"error": "AVIF encoding is not available in your Pillow build."}), 400

    try:
        quality = int(request.form.get("quality", "80"))
        if quality < 1 or quality > 100:
            raise ValueError
    except ValueError:
        return jsonify({"error": "Quality must be between 1 and 100."}), 400

    try:
        workers = int(request.form.get("workers", "12"))
        if workers < 1 or workers > 32:
            raise ValueError
    except ValueError:
        return jsonify({"error": "Parallel jobs must be between 1 and 32."}), 400

    payloads: list[tuple[str, bytes]] = []
    for f in files:
        name = f.filename or "image.jpg"
        if Path(name).suffix.lower() not in {".jpg", ".jpeg"}:
            continue
        payloads.append((name, f.read()))

    if not payloads:
        return jsonify({"error": "No valid .jpg/.jpeg files were uploaded."}), 400

    job_id = secrets.token_urlsafe(10)
    with JOBS_LOCK:
        JOBS[job_id] = {
            "state": "queued",
            "completed": 0,
            "total": len(payloads),
            "error": None,
            "zip_bytes": None,
            "format": fmt,
        }

    thread = threading.Thread(
        target=run_job,
        args=(job_id, payloads, fmt, quality, workers),
        daemon=True,
    )
    thread.start()

    return jsonify({"job_id": job_id})


@app.route("/status/<job_id>", methods=["GET"])
def status(job_id: str) -> tuple[Response, int] | Response:
    with JOBS_LOCK:
        job = JOBS.get(job_id)
        if not job:
            return jsonify({"error": "Job not found."}), 404
        return jsonify(
            {
                "state": job["state"],
                "completed": job["completed"],
                "total": job["total"],
                "error": job.get("error"),
            }
        )


@app.route("/download/<job_id>", methods=["GET"])
def download(job_id: str) -> tuple[Response, int] | Response:
    with JOBS_LOCK:
        job = JOBS.get(job_id)
        if not job:
            return jsonify({"error": "Job not found."}), 404
        if job["state"] != "done" or not job.get("zip_bytes"):
            return jsonify({"error": "Job is not ready yet."}), 400
        data = job["zip_bytes"]

    return Response(
        data,
        mimetype="application/zip",
        headers={"Content-Disposition": "attachment; filename=converted_images.zip"},
    )


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000, debug=False)
