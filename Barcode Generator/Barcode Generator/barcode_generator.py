from __future__ import annotations

import json
import os
from pathlib import Path
import tkinter as tk
from tkinter import colorchooser, filedialog, messagebox, ttk

from PIL import ImageTk

from barcode_core import (
    BARCODE_PRESETS,
    DEFAULT_PRESET_ID,
    DEFAULT_SYMBOLOGY,
    BarcodeRequest,
    build_default_filename,
    get_preset,
    render_barcode,
    resolve_unique_path,
    save_barcode_png,
    validate_barcode,
)


APP_NAME = "Barcode Generator"
PREVIEW_MAX_SIZE = (760, 360)
SETTINGS_FILENAME = "settings.json"
SURFACE_BG = "#f4efe3"
CARD_BG = "#fffaf0"
TEXT_COLOR = "#1f1b17"


class PlaceholderEntry(tk.Entry):
    def __init__(
        self,
        master: tk.Misc,
        placeholder: str,
        placeholder_color: str = "#7c7066",
        **kwargs: object,
    ) -> None:
        super().__init__(master, **kwargs)
        self.placeholder = placeholder
        self.placeholder_color = placeholder_color
        self.default_fg = str(kwargs.get("fg", TEXT_COLOR))
        self.placeholder_active = False
        self.bind("<FocusIn>", self._handle_focus_in, add="+")
        self.bind("<FocusOut>", self._handle_focus_out, add="+")
        self._show_placeholder()

    def _show_placeholder(self) -> None:
        if self.placeholder_active:
            return
        if not super().get():
            self.placeholder_active = True
            self.config(fg=self.placeholder_color)
            self.insert(0, self.placeholder)

    def _hide_placeholder(self) -> None:
        if not self.placeholder_active:
            return
        self.delete(0, tk.END)
        self.config(fg=self.default_fg)
        self.placeholder_active = False

    def _handle_focus_in(self, _: tk.Event[tk.Misc]) -> None:
        self._hide_placeholder()

    def _handle_focus_out(self, _: tk.Event[tk.Misc]) -> None:
        if not super().get().strip():
            self.delete(0, tk.END)
            self.placeholder_active = False
            self._show_placeholder()

    def value(self) -> str:
        if self.placeholder_active:
            return ""
        return super().get().strip()


def _settings_path() -> Path:
    if os.name == "nt":
        base_dir = Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming"))
        return base_dir / "BarcodeGenerator" / SETTINGS_FILENAME
    return Path.home() / ".config" / "barcode_generator" / SETTINGS_FILENAME


def _load_settings() -> dict[str, str]:
    path = _settings_path()
    if not path.exists():
        return {}
    try:
        with path.open("r", encoding="utf-8") as handle:
            data = json.load(handle)
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def _save_settings(settings: dict[str, str]) -> None:
    path = _settings_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(settings, handle, indent=2)


class BarcodeGeneratorApp:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title(APP_NAME)
        self.root.configure(bg=SURFACE_BG)
        self.root.minsize(860, 720)

        self.settings = _load_settings()
        saved_preset_id = self.settings.get("last_preset_id", DEFAULT_PRESET_ID)
        if saved_preset_id not in {preset.id for preset in BARCODE_PRESETS}:
            saved_preset_id = DEFAULT_PRESET_ID
        self.last_save_dir = self.settings.get("last_save_dir", "")
        self.advanced_visible = False
        self.current_result = None

        self.preset_label_by_id = {preset.id: preset.label for preset in BARCODE_PRESETS}
        self.preset_id_by_label = {preset.label: preset.id for preset in BARCODE_PRESETS}

        self.preset_var = tk.StringVar(value=self.preset_label_by_id[saved_preset_id])
        self.show_text_var = tk.BooleanVar(value=True)
        self.module_width_var = tk.DoubleVar(value=0.33)
        self.module_height_var = tk.DoubleVar(value=25.0)
        self.quiet_zone_var = tk.DoubleVar(value=8.0)
        self.font_size_var = tk.IntVar(value=11)

        self.barcode_color = "#000000"
        self.text_color = "#000000"
        self.background_color = "#FFFFFF"

        self._configure_styles()
        self._build_ui()
        self._apply_preset(saved_preset_id, refresh=False)
        self.update_preview()
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

    def _configure_styles(self) -> None:
        style = ttk.Style(self.root)
        style.theme_use("clam")
        style.configure("TFrame", background=SURFACE_BG)
        style.configure("Surface.TFrame", background=CARD_BG)
        style.configure("TLabelframe", background=SURFACE_BG, foreground=TEXT_COLOR)
        style.configure("TLabelframe.Label", background=SURFACE_BG, foreground=TEXT_COLOR)
        style.configure("TLabel", background=SURFACE_BG, foreground=TEXT_COLOR)
        style.configure("Card.TLabel", background=CARD_BG, foreground=TEXT_COLOR)
        style.configure(
            "Title.TLabel",
            background=CARD_BG,
            foreground=TEXT_COLOR,
            font=("Segoe UI Semibold", 22),
        )
        style.configure("Subtle.TLabel", foreground="#62584f")
        style.configure("Primary.TButton", font=("Segoe UI Semibold", 11))

    def _build_ui(self) -> None:
        self.root.grid_columnconfigure(0, weight=1)
        self.root.grid_rowconfigure(0, weight=1)

        shell = ttk.Frame(self.root, padding=18)
        shell.grid(row=0, column=0, sticky="nsew")
        shell.grid_columnconfigure(0, weight=1)
        shell.grid_rowconfigure(1, weight=1)

        hero = ttk.Frame(shell, padding=18, style="Surface.TFrame")
        hero.grid(row=0, column=0, sticky="ew", pady=(0, 14))
        hero.grid_columnconfigure(0, weight=1)

        ttk.Label(hero, text="Create a scanner-safe barcode fast.", style="Title.TLabel").grid(
            row=0, column=0, sticky="w"
        )
        ttk.Label(
            hero,
            text="Type a value, keep the preset, and save the PNG. Advanced controls stay out of the way until you need them.",
            style="Card.TLabel",
            wraplength=760,
            justify="left",
        ).grid(row=1, column=0, sticky="w", pady=(6, 18))

        ttk.Label(hero, text="Barcode Text", style="Card.TLabel").grid(
            row=2, column=0, sticky="w"
        )
        self.entry = PlaceholderEntry(
            hero,
            placeholder="Enter item code",
            font=("Segoe UI", 14),
            bg="#ffffff",
            fg=TEXT_COLOR,
            relief="solid",
            bd=1,
            insertbackground=TEXT_COLOR,
        )
        self.entry.grid(row=3, column=0, sticky="ew", pady=(6, 4), ipady=8)
        self.entry.bind("<KeyRelease>", self.update_preview, add="+")
        self.entry.bind("<FocusOut>", self.update_preview, add="+")

        ttk.Label(
            hero,
            text="Use letters, numbers, and common symbols.",
            style="Card.TLabel",
        ).grid(row=4, column=0, sticky="w", pady=(0, 12))

        preset_row = ttk.Frame(hero, style="Surface.TFrame")
        preset_row.grid(row=5, column=0, sticky="ew")
        preset_row.grid_columnconfigure(1, weight=1)

        ttk.Label(preset_row, text="Preset", style="Card.TLabel").grid(
            row=0, column=0, sticky="w", padx=(0, 10)
        )
        self.preset_combo = ttk.Combobox(
            preset_row,
            textvariable=self.preset_var,
            state="readonly",
            values=[preset.label for preset in BARCODE_PRESETS],
        )
        self.preset_combo.grid(row=0, column=1, sticky="ew")
        self.preset_combo.bind("<<ComboboxSelected>>", self._on_preset_change)

        button_row = ttk.Frame(hero, style="Surface.TFrame")
        button_row.grid(row=6, column=0, sticky="ew", pady=(16, 0))
        button_row.grid_columnconfigure(0, weight=1)
        button_row.grid_columnconfigure(1, weight=1)

        self.save_button = ttk.Button(
            button_row,
            text="Save Barcode",
            command=self.save_barcode,
            style="Primary.TButton",
            state="disabled",
        )
        self.save_button.grid(row=0, column=0, sticky="ew", padx=(0, 8))

        self.advanced_button = ttk.Button(
            button_row,
            text="Show Advanced",
            command=self.toggle_advanced,
        )
        self.advanced_button.grid(row=0, column=1, sticky="ew", padx=(8, 0))

        preview_frame = ttk.LabelFrame(shell, text="Preview", padding=14)
        preview_frame.grid(row=1, column=0, sticky="nsew")
        preview_frame.grid_columnconfigure(0, weight=1)
        preview_frame.grid_rowconfigure(0, weight=1)

        self.preview_label = tk.Label(
            preview_frame,
            text="Enter barcode text to see a live preview.",
            bg="#ffffff",
            fg=TEXT_COLOR,
            relief="flat",
            padx=18,
            pady=18,
        )
        self.preview_label.grid(row=0, column=0, sticky="nsew")

        self.size_label = ttk.Label(preview_frame, text="Export size: --")
        self.size_label.grid(row=1, column=0, sticky="w", pady=(12, 4))

        self.warning_label = ttk.Label(
            preview_frame,
            text="Black on white is the safest option for scanners.",
            style="Subtle.TLabel",
            wraplength=760,
            justify="left",
        )
        self.warning_label.grid(row=2, column=0, sticky="w")

        self.advanced_frame = ttk.LabelFrame(shell, text="Advanced", padding=14)
        self.advanced_frame.grid(row=2, column=0, sticky="ew", pady=(14, 0))
        self.advanced_frame.grid_columnconfigure(1, weight=1)
        self.advanced_frame.grid_remove()

        self._add_numeric_control(
            "Module Width (mm)",
            self.module_width_var,
            0,
            0.25,
            0.50,
            0.01,
        )
        self._add_numeric_control(
            "Module Height (mm)",
            self.module_height_var,
            1,
            20.0,
            40.0,
            1.0,
        )
        self._add_numeric_control(
            "Quiet Zone (mm)",
            self.quiet_zone_var,
            2,
            6.5,
            12.0,
            0.5,
        )
        self._add_numeric_control(
            "Font Size (pt)",
            self.font_size_var,
            3,
            10,
            14,
            1,
        )

        ttk.Checkbutton(
            self.advanced_frame,
            text="Show human-readable text",
            variable=self.show_text_var,
            command=self.update_preview,
        ).grid(row=4, column=0, columnspan=2, sticky="w", pady=(8, 8))

        self._build_color_picker_row("Bars", 5, self.pick_barcode_color)
        self._build_color_picker_row("Text", 6, self.pick_text_color)
        self._build_color_picker_row("Background", 7, self.pick_bg_color)
        self._refresh_color_swatches()

    def _add_numeric_control(
        self,
        label: str,
        variable: tk.Variable,
        row: int,
        minimum: float,
        maximum: float,
        increment: float,
    ) -> None:
        ttk.Label(self.advanced_frame, text=label).grid(
            row=row, column=0, sticky="w", pady=4
        )
        spinbox = ttk.Spinbox(
            self.advanced_frame,
            from_=minimum,
            to=maximum,
            increment=increment,
            textvariable=variable,
            width=12,
            command=self.update_preview,
        )
        spinbox.grid(row=row, column=1, sticky="w", pady=4)
        spinbox.bind("<KeyRelease>", self.update_preview, add="+")
        spinbox.bind("<FocusOut>", self.update_preview, add="+")

    def _build_color_picker_row(
        self,
        label: str,
        row: int,
        command: object,
    ) -> None:
        ttk.Label(self.advanced_frame, text=label).grid(row=row, column=0, sticky="w", pady=4)
        row_frame = ttk.Frame(self.advanced_frame)
        row_frame.grid(row=row, column=1, sticky="w", pady=4)
        swatch = tk.Label(row_frame, width=3, relief="solid", bd=1)
        swatch.grid(row=0, column=0, padx=(0, 8))
        text_label = ttk.Label(row_frame, width=10)
        text_label.grid(row=0, column=1, padx=(0, 8))
        ttk.Button(row_frame, text="Choose", command=command).grid(row=0, column=2)

        if label == "Bars":
            self.barcode_swatch = swatch
            self.barcode_label = text_label
        elif label == "Text":
            self.text_swatch = swatch
            self.text_label = text_label
        else:
            self.background_swatch = swatch
            self.background_label = text_label

    def _refresh_color_swatches(self) -> None:
        self.barcode_swatch.config(bg=self.barcode_color)
        self.barcode_label.config(text=self.barcode_color)
        self.text_swatch.config(bg=self.text_color)
        self.text_label.config(text=self.text_color)
        self.background_swatch.config(bg=self.background_color)
        self.background_label.config(text=self.background_color)

    def _selected_preset_id(self) -> str:
        return self.preset_id_by_label[self.preset_var.get()]

    def _read_numeric_value(
        self,
        variable: tk.Variable,
        label: str,
        value_type: type[float] | type[int],
    ) -> tuple[float | int | None, str]:
        raw_value = str(self.root.getvar(variable._name)).strip()
        if not raw_value:
            return None, f"{label} cannot be blank."

        try:
            numeric_value = float(raw_value)
        except ValueError:
            return None, f"{label} must be a number."

        if value_type is int:
            if not numeric_value.is_integer():
                return None, f"{label} must be a whole number."
            return int(numeric_value), ""
        return numeric_value, ""

    def _apply_preset(self, preset_id: str, refresh: bool = True) -> None:
        preset = get_preset(preset_id)
        self.preset_var.set(preset.label)
        self.module_width_var.set(preset.module_width_mm)
        self.module_height_var.set(preset.module_height_mm)
        self.quiet_zone_var.set(preset.quiet_zone_mm)
        self.font_size_var.set(preset.font_size_pt)
        self.show_text_var.set(preset.show_text)
        self.barcode_color = preset.foreground
        self.text_color = preset.text_foreground
        self.background_color = preset.background
        self._refresh_color_swatches()
        self._persist_settings()
        if refresh:
            self.update_preview()

    def _current_request(self) -> tuple[BarcodeRequest | None, str]:
        show_text = bool(self.show_text_var.get())
        preset = get_preset(self._selected_preset_id())
        text_distance = preset.text_distance_mm if show_text else 0.0

        module_width, error_message = self._read_numeric_value(
            self.module_width_var, "Module Width (mm)", float
        )
        if error_message:
            return None, error_message

        module_height, error_message = self._read_numeric_value(
            self.module_height_var, "Module Height (mm)", float
        )
        if error_message:
            return None, error_message

        quiet_zone, error_message = self._read_numeric_value(
            self.quiet_zone_var, "Quiet Zone (mm)", float
        )
        if error_message:
            return None, error_message

        font_size, error_message = self._read_numeric_value(
            self.font_size_var, "Font Size (pt)", int
        )
        if error_message:
            return None, error_message

        return BarcodeRequest(
            value=self.entry.value(),
            symbology=DEFAULT_SYMBOLOGY,
            preset_id=self._selected_preset_id(),
            overrides={
                "module_width_mm": module_width,
                "module_height_mm": module_height,
                "quiet_zone_mm": quiet_zone,
                "font_size_pt": font_size,
                "text_distance_mm": text_distance,
                "show_text": show_text,
                "foreground": self.barcode_color,
                "background": self.background_color,
                "text_foreground": self.text_color,
            },
        ), ""

    def _persist_settings(self) -> None:
        _save_settings(
            {
                "last_preset_id": self._selected_preset_id(),
                "last_save_dir": self.last_save_dir,
            }
        )

    def _on_preset_change(self, _: tk.Event[tk.Misc]) -> None:
        self._apply_preset(self._selected_preset_id())

    def toggle_advanced(self) -> None:
        self.advanced_visible = not self.advanced_visible
        if self.advanced_visible:
            self.advanced_frame.grid()
            self.advanced_button.config(text="Hide Advanced")
        else:
            self.advanced_frame.grid_remove()
            self.advanced_button.config(text="Show Advanced")

    def pick_barcode_color(self) -> None:
        color = colorchooser.askcolor(color=self.barcode_color)[1]
        if color:
            self.barcode_color = color.upper()
            self._refresh_color_swatches()
            self.update_preview()

    def pick_text_color(self) -> None:
        color = colorchooser.askcolor(color=self.text_color)[1]
        if color:
            self.text_color = color.upper()
            self._refresh_color_swatches()
            self.update_preview()

    def pick_bg_color(self) -> None:
        color = colorchooser.askcolor(color=self.background_color)[1]
        if color:
            self.background_color = color.upper()
            self._refresh_color_swatches()
            self.update_preview()

    def update_preview(self, *_: object) -> None:
        request, request_error = self._current_request()
        if request_error:
            self.preview_label.configure(image="", text=request_error)
            self.preview_label.image = None
            self.size_label.config(text="Export size: --")
            self.warning_label.config(text="Fix the advanced settings and try again.")
            self.save_button.state(["disabled"])
            self.current_result = None
            return

        validation = validate_barcode(request)
        if not validation.is_valid:
            message = validation.message if request.value else "Enter barcode text"
            self.preview_label.configure(image="", text=message)
            self.preview_label.image = None
            self.size_label.config(text="Export size: --")
            self.warning_label.config(
                text="Black on white is the safest option for scanners."
            )
            self.save_button.state(["disabled"])
            self.current_result = None
            return

        try:
            result = render_barcode(request)
        except Exception as exc:
            self.preview_label.configure(image="", text=f"Preview unavailable: {exc}")
            self.preview_label.image = None
            self.size_label.config(text="Export size: --")
            self.warning_label.config(text="Check the barcode text and try again.")
            self.save_button.state(["disabled"])
            self.current_result = None
            return

        preview_image = result.image.copy()
        preview_image.thumbnail(PREVIEW_MAX_SIZE)
        tk_image = ImageTk.PhotoImage(preview_image)
        self.preview_label.configure(image=tk_image, text="")
        self.preview_label.image = tk_image
        self.size_label.config(
            text=f"Export size: {result.pixel_width} x {result.pixel_height} px"
        )
        warning_text = "Black on white is the safest option for scanners."
        if result.warnings:
            warning_text = " ".join(result.warnings)
        self.warning_label.config(text=warning_text)
        self.save_button.state(["!disabled"])
        self.current_result = result

    def save_barcode(self) -> None:
        request, request_error = self._current_request()
        if request_error:
            messagebox.showerror("Error", request_error)
            return

        validation = validate_barcode(request)
        if not validation.is_valid:
            messagebox.showerror("Error", validation.message)
            return

        if self.current_result is None:
            self.update_preview()
        if self.current_result is None:
            messagebox.showerror("Error", "Could not render the barcode.")
            return

        initial_dir = self.last_save_dir or str(Path.cwd())
        default_name = build_default_filename(request.value)
        chosen_path = filedialog.asksaveasfilename(
            title="Save Barcode As",
            defaultextension=".png",
            initialfile=default_name,
            initialdir=initial_dir,
            filetypes=[("PNG Image", "*.png")],
        )
        if not chosen_path:
            return

        output_path = resolve_unique_path(chosen_path)
        try:
            save_barcode_png(self.current_result, output_path)
        except Exception as exc:
            messagebox.showerror("Error", f"Could not save barcode: {exc}")
            return

        self.last_save_dir = str(output_path.parent)
        self._persist_settings()
        saved_message = f"Barcode saved as {output_path}"
        if str(output_path) != chosen_path:
            saved_message += "\n\nThe file already existed, so a timestamp was added."
        messagebox.showinfo("Saved", saved_message)

    def _on_close(self) -> None:
        self._persist_settings()
        self.root.destroy()


def main() -> None:
    root = tk.Tk()
    BarcodeGeneratorApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
