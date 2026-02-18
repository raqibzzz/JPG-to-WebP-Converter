# JPG/JPEG to WebP/AVIF Converter

A simple CLI tool to convert `.jpg` and `.jpeg` images into WebP, AVIF, or both.

## Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Usage

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
