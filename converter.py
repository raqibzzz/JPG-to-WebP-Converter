#!/usr/bin/env python3
"""Convert JPG/JPEG images to WebP and/or AVIF."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Iterable, List

from PIL import Image

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Convert .jpg/.jpeg files to WebP and/or AVIF."
    )
    parser.add_argument(
        "inputs",
        nargs="+",
        help="One or more files/directories containing JPG/JPEG images.",
    )
    parser.add_argument(
        "-f",
        "--format",
        choices=["webp", "avif", "both"],
        default="both",
        help="Output format to create (default: both).",
    )
    parser.add_argument(
        "-q",
        "--quality",
        type=int,
        default=80,
        help="Quality for output files, 1-100 (default: 80).",
    )
    parser.add_argument(
        "-o",
        "--output-dir",
        default=None,
        help=(
            "Optional output directory. If omitted, converted files are written "
            "next to source files."
        ),
    )
    parser.add_argument(
        "-r",
        "--recursive",
        action="store_true",
        help="Scan directories recursively.",
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Overwrite existing output files.",
    )
    return parser.parse_args()


def validate_quality(quality: int) -> None:
    if not 1 <= quality <= 100:
        raise ValueError("Quality must be between 1 and 100.")


def collect_jpeg_files(paths: Iterable[str], recursive: bool) -> List[Path]:
    out: List[Path] = []
    suffixes = {".jpg", ".jpeg"}

    for raw in paths:
        p = Path(raw).expanduser().resolve()
        if not p.exists():
            print(f"[WARN] Not found: {p}", file=sys.stderr)
            continue

        if p.is_file() and p.suffix.lower() in suffixes:
            out.append(p)
            continue

        if p.is_dir():
            globber = p.rglob if recursive else p.glob
            for candidate in globber("*"):
                if candidate.is_file() and candidate.suffix.lower() in suffixes:
                    out.append(candidate.resolve())
            continue

        print(f"[WARN] Unsupported input (not JPG/JPEG): {p}", file=sys.stderr)

    unique = sorted(set(out))
    return unique


def save_image(
    src: Path,
    dest: Path,
    fmt: str,
    quality: int,
    overwrite: bool,
) -> bool:
    if dest.exists() and not overwrite:
        print(f"[SKIP] Exists: {dest}")
        return False

    dest.parent.mkdir(parents=True, exist_ok=True)

    with Image.open(src) as im:
        # JPEG never has alpha, but convert to RGB to avoid mode issues.
        im = im.convert("RGB")
        im.save(dest, format=fmt.upper(), quality=quality)

    print(f"[OK] {src.name} -> {dest}")
    return True


def build_output_path(src: Path, output_dir: Path | None, ext: str) -> Path:
    if output_dir is None:
        return src.with_suffix(ext)
    return output_dir / f"{src.stem}{ext}"


def main() -> int:
    args = parse_args()

    try:
        validate_quality(args.quality)
    except ValueError as err:
        print(f"[ERROR] {err}", file=sys.stderr)
        return 2

    targets = collect_jpeg_files(args.inputs, recursive=args.recursive)
    if not targets:
        print("[ERROR] No JPG/JPEG files found.", file=sys.stderr)
        return 1

    output_dir = Path(args.output_dir).expanduser().resolve() if args.output_dir else None

    formats = ["webp", "avif"] if args.format == "both" else [args.format]

    converted = 0
    for src in targets:
        for fmt in formats:
            ext = ".webp" if fmt == "webp" else ".avif"
            dest = build_output_path(src, output_dir, ext)
            try:
                converted += int(
                    save_image(
                        src=src,
                        dest=dest,
                        fmt=fmt,
                        quality=args.quality,
                        overwrite=args.overwrite,
                    )
                )
            except (KeyError, OSError):
                if fmt == "avif":
                    print(
                        "[ERROR] AVIF encoding is not available. "
                        "Install pillow-avif-plugin (or a Pillow build with AVIF support).",
                        file=sys.stderr,
                    )
                    return 3
                raise

    print(f"Done. Converted {converted} file(s).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
