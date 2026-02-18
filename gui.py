#!/usr/bin/env python3
"""Tkinter GUI for converting JPG/JPEG to WebP and AVIF in parallel."""

from __future__ import annotations

import io
import os
import queue
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from PIL import Image


def has_avif_encoder() -> bool:
    try:
        buf = io.BytesIO()
        Image.new("RGB", (1, 1), color=(0, 0, 0)).save(buf, format="AVIF")
        return True
    except Exception:
        return False


class ConverterGUI(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title("JPG/JPEG to WebP/AVIF Converter")
        self.geometry("900x620")
        self.minsize(860, 560)

        self.selected_files: list[Path] = []
        self.ui_queue: queue.Queue = queue.Queue()
        self.total_tasks = 0
        self.completed_tasks = 0
        self.success_count = 0
        self.error_count = 0
        self.skip_count = 0
        self.is_running = False

        default_workers = min(8, max(2, os.cpu_count() or 4))

        self.format_var = tk.StringVar(value="both")
        self.quality_var = tk.IntVar(value=80)
        self.recursive_var = tk.BooleanVar(value=True)
        self.overwrite_var = tk.BooleanVar(value=False)
        self.output_dir_var = tk.StringVar(value="")
        self.workers_var = tk.IntVar(value=default_workers)

        self._build_ui()

    def _build_ui(self) -> None:
        self.columnconfigure(0, weight=1)
        self.rowconfigure(1, weight=1)

        top = ttk.Frame(self, padding=10)
        top.grid(row=0, column=0, sticky="ew")
        top.columnconfigure(0, weight=1)

        actions = ttk.Frame(top)
        actions.grid(row=0, column=0, sticky="w")

        self.add_files_btn = ttk.Button(actions, text="Add Images", command=self.add_files)
        self.add_files_btn.grid(row=0, column=0, padx=(0, 6))

        self.add_folder_btn = ttk.Button(actions, text="Add Folder", command=self.add_folder)
        self.add_folder_btn.grid(row=0, column=1, padx=(0, 6))

        self.remove_btn = ttk.Button(actions, text="Remove Selected", command=self.remove_selected)
        self.remove_btn.grid(row=0, column=2, padx=(0, 6))

        self.clear_btn = ttk.Button(actions, text="Clear", command=self.clear_all)
        self.clear_btn.grid(row=0, column=3)

        options = ttk.Frame(top)
        options.grid(row=1, column=0, sticky="ew", pady=(10, 0))

        ttk.Label(options, text="Format:").grid(row=0, column=0, sticky="w")
        self.format_combo = ttk.Combobox(
            options,
            textvariable=self.format_var,
            values=["webp", "avif", "both"],
            state="readonly",
            width=10,
        )
        self.format_combo.grid(row=0, column=1, padx=(6, 16), sticky="w")

        ttk.Label(options, text="Quality:").grid(row=0, column=2, sticky="w")
        self.quality_spin = ttk.Spinbox(options, from_=1, to=100, textvariable=self.quality_var, width=6)
        self.quality_spin.grid(row=0, column=3, padx=(6, 16), sticky="w")

        ttk.Label(options, text="Parallel jobs:").grid(row=0, column=4, sticky="w")
        self.workers_spin = ttk.Spinbox(options, from_=1, to=32, textvariable=self.workers_var, width=6)
        self.workers_spin.grid(row=0, column=5, padx=(6, 16), sticky="w")

        self.recursive_check = ttk.Checkbutton(options, text="Recursive folders", variable=self.recursive_var)
        self.recursive_check.grid(row=0, column=6, padx=(0, 16), sticky="w")

        self.overwrite_check = ttk.Checkbutton(options, text="Overwrite output", variable=self.overwrite_var)
        self.overwrite_check.grid(row=0, column=7, sticky="w")

        output = ttk.Frame(top)
        output.grid(row=2, column=0, sticky="ew", pady=(10, 0))
        output.columnconfigure(1, weight=1)

        ttk.Label(output, text="Output folder (optional):").grid(row=0, column=0, sticky="w")
        self.output_entry = ttk.Entry(output, textvariable=self.output_dir_var)
        self.output_entry.grid(row=0, column=1, padx=(8, 8), sticky="ew")
        self.browse_output_btn = ttk.Button(output, text="Browse", command=self.browse_output)
        self.browse_output_btn.grid(row=0, column=2)

        center = ttk.Frame(self, padding=(10, 0, 10, 0))
        center.grid(row=1, column=0, sticky="nsew")
        center.rowconfigure(0, weight=3)
        center.rowconfigure(1, weight=2)
        center.columnconfigure(0, weight=1)

        files_frame = ttk.LabelFrame(center, text="Selected Images")
        files_frame.grid(row=0, column=0, sticky="nsew")
        files_frame.rowconfigure(0, weight=1)
        files_frame.columnconfigure(0, weight=1)

        self.files_list = tk.Listbox(files_frame, selectmode=tk.EXTENDED)
        self.files_list.grid(row=0, column=0, sticky="nsew", padx=(8, 0), pady=8)
        file_scroll = ttk.Scrollbar(files_frame, orient=tk.VERTICAL, command=self.files_list.yview)
        file_scroll.grid(row=0, column=1, sticky="ns", padx=(0, 8), pady=8)
        self.files_list.configure(yscrollcommand=file_scroll.set)

        self.count_label = ttk.Label(center, text="0 images selected")
        self.count_label.grid(row=0, column=0, sticky="sw", padx=2, pady=(0, 4))

        log_frame = ttk.LabelFrame(center, text="Log")
        log_frame.grid(row=1, column=0, sticky="nsew", pady=(8, 0))
        log_frame.rowconfigure(0, weight=1)
        log_frame.columnconfigure(0, weight=1)

        self.log_text = tk.Text(log_frame, height=10, wrap="word", state="disabled")
        self.log_text.grid(row=0, column=0, sticky="nsew", padx=(8, 0), pady=8)
        log_scroll = ttk.Scrollbar(log_frame, orient=tk.VERTICAL, command=self.log_text.yview)
        log_scroll.grid(row=0, column=1, sticky="ns", padx=(0, 8), pady=8)
        self.log_text.configure(yscrollcommand=log_scroll.set)

        bottom = ttk.Frame(self, padding=10)
        bottom.grid(row=2, column=0, sticky="ew")
        bottom.columnconfigure(0, weight=1)

        self.progress = ttk.Progressbar(bottom, mode="determinate")
        self.progress.grid(row=0, column=0, sticky="ew", padx=(0, 10))

        self.progress_label = ttk.Label(bottom, text="Idle")
        self.progress_label.grid(row=0, column=1, padx=(0, 10))

        self.start_btn = ttk.Button(bottom, text="Start Conversion", command=self.start_conversion)
        self.start_btn.grid(row=0, column=2)

    def add_files(self) -> None:
        paths = filedialog.askopenfilenames(
            title="Select JPG/JPEG files",
            filetypes=[("JPEG files", "*.jpg *.jpeg *.JPG *.JPEG")],
        )
        self._merge_files(Path(p).resolve() for p in paths)

    def add_folder(self) -> None:
        folder = filedialog.askdirectory(title="Select folder")
        if not folder:
            return

        root = Path(folder).resolve()
        globber = root.rglob if self.recursive_var.get() else root.glob
        files = [
            p.resolve()
            for p in globber("*")
            if p.is_file() and p.suffix.lower() in {".jpg", ".jpeg"}
        ]
        self._merge_files(files)

    def remove_selected(self) -> None:
        selected_indices = list(self.files_list.curselection())
        if not selected_indices:
            return

        selected_paths = {Path(self.files_list.get(i)) for i in selected_indices}
        self.selected_files = [p for p in self.selected_files if p not in selected_paths]
        self._refresh_file_list()

    def clear_all(self) -> None:
        self.selected_files = []
        self._refresh_file_list()

    def browse_output(self) -> None:
        folder = filedialog.askdirectory(title="Select output folder")
        if folder:
            self.output_dir_var.set(folder)

    def _merge_files(self, files) -> None:
        existing = set(self.selected_files)
        for file_path in files:
            if file_path.suffix.lower() in {".jpg", ".jpeg"} and file_path.exists():
                existing.add(file_path)

        self.selected_files = sorted(existing)
        self._refresh_file_list()

    def _refresh_file_list(self) -> None:
        self.files_list.delete(0, tk.END)
        for p in self.selected_files:
            self.files_list.insert(tk.END, str(p))
        self.count_label.configure(text=f"{len(self.selected_files)} images selected")

    def _append_log(self, message: str) -> None:
        self.log_text.configure(state="normal")
        self.log_text.insert(tk.END, message + "\n")
        self.log_text.see(tk.END)
        self.log_text.configure(state="disabled")

    def _set_controls_enabled(self, enabled: bool) -> None:
        state = "normal" if enabled else "disabled"
        combo_state = "readonly" if enabled else "disabled"

        for widget in [
            self.add_files_btn,
            self.add_folder_btn,
            self.remove_btn,
            self.clear_btn,
            self.quality_spin,
            self.workers_spin,
            self.recursive_check,
            self.overwrite_check,
            self.output_entry,
            self.browse_output_btn,
            self.start_btn,
        ]:
            widget.configure(state=state)

        self.format_combo.configure(state=combo_state)

    def start_conversion(self) -> None:
        if self.is_running:
            return

        if not self.selected_files:
            messagebox.showerror("No files", "Please add at least one JPG/JPEG image.")
            return

        try:
            quality = int(self.quality_var.get())
            if quality < 1 or quality > 100:
                raise ValueError
        except ValueError:
            messagebox.showerror("Invalid quality", "Quality must be between 1 and 100.")
            return

        try:
            workers = int(self.workers_var.get())
            if workers < 1 or workers > 32:
                raise ValueError
        except ValueError:
            messagebox.showerror("Invalid workers", "Parallel jobs must be between 1 and 32.")
            return

        formats = ["webp", "avif"] if self.format_var.get() == "both" else [self.format_var.get()]

        if "avif" in formats and not has_avif_encoder():
            messagebox.showerror(
                "AVIF unsupported",
                "AVIF encoding is not available in your Pillow installation.",
            )
            return

        output_dir = None
        raw_out = self.output_dir_var.get().strip()
        if raw_out:
            output_dir = Path(raw_out).expanduser().resolve()
            output_dir.mkdir(parents=True, exist_ok=True)

        self.is_running = True
        self.total_tasks = len(self.selected_files) * len(formats)
        self.completed_tasks = 0
        self.success_count = 0
        self.error_count = 0
        self.skip_count = 0

        self.progress.configure(value=0, maximum=self.total_tasks)
        self.progress_label.configure(text=f"0/{self.total_tasks}")
        self._append_log(
            f"Starting conversion: {len(self.selected_files)} images, {len(formats)} format(s), {workers} parallel jobs"
        )

        self._set_controls_enabled(False)

        thread = threading.Thread(
            target=self._run_conversion,
            args=(self.selected_files.copy(), formats, quality, output_dir, self.overwrite_var.get(), workers),
            daemon=True,
        )
        thread.start()
        self.after(100, self._drain_queue)

    def _run_conversion(
        self,
        files: list[Path],
        formats: list[str],
        quality: int,
        output_dir: Path | None,
        overwrite: bool,
        workers: int,
    ) -> None:
        def convert_one(src: Path, dest: Path, fmt: str) -> tuple[str, str]:
            if dest.exists() and not overwrite:
                return "skip", f"[SKIP] {dest}"

            dest.parent.mkdir(parents=True, exist_ok=True)
            with Image.open(src) as im:
                im.convert("RGB").save(dest, format=fmt.upper(), quality=quality)

            return "ok", f"[OK] {src.name} -> {dest}"

        def choose_dest(src: Path, fmt: str, claimed: set[Path]) -> Path:
            ext = ".webp" if fmt == "webp" else ".avif"
            if output_dir is None:
                return src.with_suffix(ext)

            candidate = output_dir / f"{src.stem}{ext}"
            if candidate not in claimed:
                claimed.add(candidate)
                return candidate

            index = 2
            while True:
                candidate = output_dir / f"{src.stem}_{index}{ext}"
                if candidate not in claimed:
                    claimed.add(candidate)
                    return candidate
                index += 1

        futures = []
        claimed_paths: set[Path] = set()
        with ThreadPoolExecutor(max_workers=workers) as executor:
            for src in files:
                for fmt in formats:
                    dest = choose_dest(src, fmt, claimed_paths)
                    futures.append(executor.submit(convert_one, src, dest, fmt))

            for future in as_completed(futures):
                try:
                    status, message = future.result()
                    self.ui_queue.put(("item", status, message))
                except Exception as err:
                    self.ui_queue.put(("item", "error", f"[ERROR] {err}"))

        self.ui_queue.put(("done", None, None))

    def _drain_queue(self) -> None:
        while True:
            try:
                event, status, message = self.ui_queue.get_nowait()
            except queue.Empty:
                break

            if event == "item":
                self.completed_tasks += 1
                if status == "ok":
                    self.success_count += 1
                elif status == "skip":
                    self.skip_count += 1
                else:
                    self.error_count += 1

                self.progress.configure(value=self.completed_tasks)
                self.progress_label.configure(text=f"{self.completed_tasks}/{self.total_tasks}")
                self._append_log(message)

            elif event == "done":
                self.is_running = False
                self._set_controls_enabled(True)
                summary = (
                    f"Done. Success: {self.success_count}, "
                    f"Skipped: {self.skip_count}, Errors: {self.error_count}"
                )
                self._append_log(summary)
                messagebox.showinfo("Conversion complete", summary)

        if self.is_running:
            self.after(100, self._drain_queue)


def main() -> None:
    app = ConverterGUI()
    app.mainloop()


if __name__ == "__main__":
    main()
