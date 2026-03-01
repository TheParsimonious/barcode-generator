from __future__ import annotations

from dataclasses import dataclass, fields, replace
from datetime import datetime
import io
import json
from pathlib import Path
import re
from typing import Any

import barcode
from barcode.writer import ImageWriter, mm2px, pt2mm
from PIL import Image, ImageFont


CONFIG_PATH = Path(__file__).with_name("barcode_presets.json")
DEFAULT_FONT_NAME = "DejaVuSans.ttf"
SAFE_FOREGROUND = "#000000"
SAFE_BACKGROUND = "#FFFFFF"
ADVANCED_LIMITS = {
    "module_width_mm": (0.25, 0.50),
    "module_height_mm": (20.0, 40.0),
    "quiet_zone_mm": (6.5, 12.0),
    "font_size_pt": (10, 14),
}


class CustomImageWriter(ImageWriter):
    def __init__(self, format: str = "PNG", mode: str = "RGB") -> None:
        super().__init__(format=format, mode=mode)
        self.text_foreground = self.foreground

    def _load_font(self, font_size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
        try:
            return ImageFont.truetype(DEFAULT_FONT_NAME, font_size)
        except OSError:
            if self.font_path:
                try:
                    return ImageFont.truetype(self.font_path, font_size)
                except OSError:
                    pass
        return ImageFont.load_default()

    def _paint_text(self, xpos: float, ypos: float) -> None:
        font_size = int(mm2px(pt2mm(self.font_size), self.dpi))
        font = self._load_font(font_size)
        for subtext in self.text.split("\n"):
            pos = (mm2px(xpos, self.dpi), mm2px(ypos, self.dpi))
            self._draw.text(
                pos,
                subtext,
                font=font,
                fill=self.text_foreground,
                anchor="md",
            )
            ypos += pt2mm(self.font_size) / 2 + self.text_line_distance


@dataclass(frozen=True)
class BarcodePreset:
    id: str
    label: str
    module_width_mm: float
    module_height_mm: float
    quiet_zone_mm: float
    font_size_pt: int
    text_distance_mm: float
    show_text: bool
    foreground: str
    background: str
    text_foreground: str


@dataclass(frozen=True)
class BarcodeRequest:
    value: str
    symbology: str = "code128"
    preset_id: str = ""
    overrides: dict[str, bool | float | str] | None = None


@dataclass(frozen=True)
class ValidationResult:
    is_valid: bool
    message: str
    warnings: tuple[str, ...] = ()


@dataclass(frozen=True)
class RenderResult:
    image: Image.Image
    pixel_width: int
    pixel_height: int
    warnings: tuple[str, ...] = ()


def _load_config() -> dict[str, Any]:
    with CONFIG_PATH.open("r", encoding="utf-8") as handle:
        return json.load(handle)


CONFIG = _load_config()
DEFAULT_SYMBOLOGY = str(CONFIG["symbology"]).lower()
DEFAULT_PRESET_ID = str(CONFIG["default_preset_id"])
DESKTOP_MAX_LENGTH = int(CONFIG["desktop_max_length"])
WEB_MAX_LENGTH = int(CONFIG["web_max_length"])
WEB_RECOMMENDED_LENGTH = int(CONFIG["web_recommended_length"])
WEB_WARNING_MESSAGE = str(CONFIG["web_warning_message"])

BARCODE_PRESETS = tuple(
    BarcodePreset(
        id=item["id"],
        label=item["label"],
        module_width_mm=float(item["module_width_mm"]),
        module_height_mm=float(item["module_height_mm"]),
        quiet_zone_mm=float(item["quiet_zone_mm"]),
        font_size_pt=int(item["font_size_pt"]),
        text_distance_mm=float(item["text_distance_mm"]),
        show_text=bool(item["show_text"]),
        foreground=str(item["foreground"]).upper(),
        background=str(item["background"]).upper(),
        text_foreground=str(item["text_foreground"]).upper(),
    )
    for item in CONFIG["presets"]
)
PRESET_LOOKUP = {preset.id: preset for preset in BARCODE_PRESETS}


def _normalize_color(color: str) -> str:
    return color.strip().upper()


def get_preset(preset_id: str) -> BarcodePreset:
    return PRESET_LOOKUP[preset_id]


def safe_filename(base: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "_", base.strip())
    return cleaned[:100] or "barcode"


def build_default_filename(value: str) -> str:
    return f"barcode_{safe_filename(value)}.png"


def resolve_unique_path(path: str | Path) -> Path:
    original = Path(path)
    if not original.exists():
        return original

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    candidate = original.with_name(f"{original.stem}_{timestamp}{original.suffix}")
    counter = 2
    while candidate.exists():
        candidate = original.with_name(
            f"{original.stem}_{timestamp}_{counter}{original.suffix}"
        )
        counter += 1
    return candidate


def _clamp_float(value: float, minimum: float, maximum: float) -> float:
    return max(minimum, min(maximum, float(value)))


def _clamp_int(value: int, minimum: int, maximum: int) -> int:
    return max(minimum, min(maximum, int(value)))


def _coerce_bool(value: bool | float | str) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "on"}
    return bool(value)


def _effective_preset(request: BarcodeRequest) -> tuple[BarcodePreset, tuple[str, ...]]:
    base_preset = get_preset(request.preset_id)
    updated_values = {
        field.name: getattr(base_preset, field.name)
        for field in fields(BarcodePreset)
    }
    overrides = request.overrides or {}

    if "module_width_mm" in overrides:
        updated_values["module_width_mm"] = _clamp_float(
            float(overrides["module_width_mm"]),
            *ADVANCED_LIMITS["module_width_mm"],
        )
    if "module_height_mm" in overrides:
        updated_values["module_height_mm"] = _clamp_float(
            float(overrides["module_height_mm"]),
            *ADVANCED_LIMITS["module_height_mm"],
        )
    if "quiet_zone_mm" in overrides:
        updated_values["quiet_zone_mm"] = _clamp_float(
            float(overrides["quiet_zone_mm"]),
            *ADVANCED_LIMITS["quiet_zone_mm"],
        )
    if "font_size_pt" in overrides:
        updated_values["font_size_pt"] = _clamp_int(
            int(float(overrides["font_size_pt"])),
            *ADVANCED_LIMITS["font_size_pt"],
        )
    if "text_distance_mm" in overrides:
        updated_values["text_distance_mm"] = max(0.0, float(overrides["text_distance_mm"]))
    if "show_text" in overrides:
        updated_values["show_text"] = _coerce_bool(overrides["show_text"])
    if "foreground" in overrides:
        updated_values["foreground"] = _normalize_color(str(overrides["foreground"]))
    if "background" in overrides:
        updated_values["background"] = _normalize_color(str(overrides["background"]))
    if "text_foreground" in overrides:
        updated_values["text_foreground"] = _normalize_color(
            str(overrides["text_foreground"])
        )

    effective_preset = replace(base_preset, **updated_values)
    warnings: list[str] = []
    if (
        effective_preset.foreground != SAFE_FOREGROUND
        or effective_preset.background != SAFE_BACKGROUND
        or effective_preset.text_foreground != SAFE_FOREGROUND
    ):
        warnings.append("Custom colors may reduce scan reliability")
    return effective_preset, tuple(warnings)


def validate_barcode(request: BarcodeRequest) -> ValidationResult:
    value = request.value.strip()
    if not value:
        return ValidationResult(False, "Enter barcode text")
    if request.symbology.lower() != DEFAULT_SYMBOLOGY:
        return ValidationResult(False, "Only Code128 barcodes are supported")
    if request.preset_id not in PRESET_LOOKUP:
        return ValidationResult(False, "Unknown barcode preset")
    if len(value) > DESKTOP_MAX_LENGTH:
        return ValidationResult(
            False, f"Barcode text must be <= {DESKTOP_MAX_LENGTH} characters"
        )
    try:
        value.encode("ascii")
    except UnicodeEncodeError:
        return ValidationResult(False, "Only ASCII characters are allowed")
    if any(ord(character) < 32 or ord(character) > 126 for character in value):
        return ValidationResult(False, "Only printable ASCII characters are allowed")
    return ValidationResult(True, "")


def _writer_options(preset: BarcodePreset) -> dict[str, object]:
    text_distance = preset.text_distance_mm if preset.show_text else 0.0
    return {
        "module_width": preset.module_width_mm,
        "module_height": preset.module_height_mm,
        "quiet_zone": preset.quiet_zone_mm,
        "font_size": preset.font_size_pt,
        "text_distance": text_distance,
        "write_text": preset.show_text,
        "background": preset.background,
        "foreground": preset.foreground,
        "text_foreground": preset.text_foreground,
    }


def render_barcode(request: BarcodeRequest) -> RenderResult:
    validation = validate_barcode(request)
    if not validation.is_valid:
        raise ValueError(validation.message)

    effective_preset, warnings = _effective_preset(request)
    code_class = barcode.get_barcode_class(DEFAULT_SYMBOLOGY)
    buffer = io.BytesIO()
    try:
        code = code_class(request.value.strip(), writer=CustomImageWriter())
        code.write(buffer, _writer_options(effective_preset))
        buffer.seek(0)
        opened_image = Image.open(buffer)
        image = opened_image.convert("RGB")
        opened_image.close()
        return RenderResult(
            image=image,
            pixel_width=image.width,
            pixel_height=image.height,
            warnings=warnings,
        )
    finally:
        buffer.close()


def save_barcode_png(result: RenderResult, path: str | Path) -> None:
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    result.image.save(output_path, format="PNG")
