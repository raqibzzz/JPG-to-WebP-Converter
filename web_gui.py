#!/usr/bin/env python3
"""Browser-based GUI for converting JPG/JPEG to WebP/AVIF in parallel."""

from __future__ import annotations

import io
import zipfile
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from flask import Flask, Response, render_template_string, request
from PIL import Image

app = Flask(__name__)

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
    .note { margin-top: 10px; color: var(--muted); font-size: 0.9rem; }
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
    <p>Upload 20-30 images (or more), choose parallel jobs, then download one ZIP file.</p>

    <form method="post" enctype="multipart/form-data">
      <div>
        <label for="files">Images (.jpg/.jpeg)</label>
        <input id="files" name="files" type="file" multiple accept=".jpg,.jpeg,.JPG,.JPEG" required />
      </div>

      <div class="grid" style="margin-top: 12px;">
        <div>
          <label for="format">Format</label>
          <select id="format" name="format">
            <option value="both">WebP + AVIF</option>
            <option value="webp">WebP only</option>
            <option value="avif">AVIF only</option>
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

      <button type="submit">Convert and Download ZIP</button>
      <div class="note">Recommended for 20-30 images: 8-16 parallel jobs.</div>

      {% if error %}
      <div class="error">{{ error }}</div>
      {% endif %}
    </form>
  </main>
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


@app.route("/", methods=["GET", "POST"])
def index() -> Response | str:
    if request.method == "GET":
        return render_template_string(HTML, error=None)

    files = request.files.getlist("files")
    if not files:
        return render_template_string(HTML, error="Please upload at least one image.")

    fmt = request.form.get("format", "both")
    if fmt not in {"webp", "avif", "both"}:
        return render_template_string(HTML, error="Invalid format selected.")

    try:
        quality = int(request.form.get("quality", "80"))
        if quality < 1 or quality > 100:
            raise ValueError
    except ValueError:
        return render_template_string(HTML, error="Quality must be between 1 and 100.")

    try:
        workers = int(request.form.get("workers", "12"))
        if workers < 1 or workers > 32:
            raise ValueError
    except ValueError:
        return render_template_string(HTML, error="Parallel jobs must be between 1 and 32.")

    formats = ["webp", "avif"] if fmt == "both" else [fmt]
    if "avif" in formats and not avif_available():
        return render_template_string(HTML, error="AVIF encoding is not available in your Pillow build.")

    payloads: list[tuple[str, bytes]] = []
    for f in files:
        name = f.filename or "image.jpg"
        if Path(name).suffix.lower() not in {".jpg", ".jpeg"}:
            continue
        payloads.append((name, f.read()))

    if not payloads:
        return render_template_string(HTML, error="No valid .jpg/.jpeg files were uploaded.")

    jobs: list[tuple[str, bytes, str]] = []
    for name, raw in payloads:
        for one_fmt in formats:
            jobs.append((name, raw, one_fmt))

    results: list[tuple[str, bytes]] = []
    name_counts: dict[str, int] = {}

    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = [pool.submit(convert_one, raw, name, one_fmt, quality) for name, raw, one_fmt in jobs]
        for fut in as_completed(futures):
            out_name, out_data = fut.result()
            # Avoid ZIP name collisions for same stem names.
            if out_name in name_counts:
                name_counts[out_name] += 1
                stem = Path(out_name).stem
                ext = Path(out_name).suffix
                safe_name = f"{stem}_{name_counts[out_name]}{ext}"
            else:
                name_counts[out_name] = 1
                safe_name = out_name
            results.append((safe_name, out_data))

    zip_buf = io.BytesIO()
    with zipfile.ZipFile(zip_buf, mode="w", compression=zipfile.ZIP_DEFLATED) as zf:
        for out_name, out_data in sorted(results):
            zf.writestr(out_name, out_data)

    zip_buf.seek(0)
    return Response(
        zip_buf.getvalue(),
        mimetype="application/zip",
        headers={"Content-Disposition": "attachment; filename=converted_images.zip"},
    )


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000, debug=False)
