# JPG/JPEG to WebP/AVIF Converter

A converter for `.jpg` and `.jpeg` images into WebP, AVIF, or both.
Includes:
- A browser GUI for batch conversion with parallel processing
- A desktop Tk GUI
- A CLI

## Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
```

## Usage

### GUI (recommended)

Launch the browser GUI:

```bash
python3 web_gui.py
```

Then open:

- [http://127.0.0.1:5000](http://127.0.0.1:5000)

In the browser GUI:

- Add 20-30 images at once (multi-file upload)
- Choose format (`webp`, `avif`, or `both`)
- Set quality and `Parallel jobs` (set to `8-16` for 20-30 images)
- Click **Convert and Download ZIP**

### Desktop GUI (Tk)

```bash
python3 gui.py
```

### CLI

Convert one image to both formats:

```bash
python3 converter.py photo.jpg
```

Convert a folder recursively to WebP only:

```bash
python3 converter.py ./images -r -f webp
```

Convert to AVIF with quality 70 into an output folder:

```bash
python3 converter.py ./images -r -f avif -q 70 -o ./converted
```

Overwrite already converted files:

```bash
python3 converter.py ./images -r --overwrite
```

## Options

- `inputs` one or more files/folders
- `-f, --format` `webp`, `avif`, or `both` (default)
- `-q, --quality` quality 1-100 (default: 80)
- `-o, --output-dir` output directory
- `-r, --recursive` recurse through subfolders
- `--overwrite` overwrite existing output files

## Notes

- AVIF support depends on Pillow build/plugin availability.
- This tool only reads `.jpg` and `.jpeg` inputs.
- GUI supports parallel conversion jobs so 20-30 image batches can be processed concurrently.
