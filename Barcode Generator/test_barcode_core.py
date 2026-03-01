from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

from barcode_core import (
    DEFAULT_PRESET_ID,
    BarcodeRequest,
    build_default_filename,
    render_barcode,
    resolve_unique_path,
    validate_barcode,
)


class BarcodeCoreTests(unittest.TestCase):
    def test_validate_rejects_empty_value(self) -> None:
        result = validate_barcode(BarcodeRequest(value="", preset_id=DEFAULT_PRESET_ID))
        self.assertFalse(result.is_valid)
        self.assertEqual(result.message, "Enter barcode text")

    def test_validate_rejects_non_ascii_value(self) -> None:
        result = validate_barcode(BarcodeRequest(value="CAFÉ", preset_id=DEFAULT_PRESET_ID))
        self.assertFalse(result.is_valid)
        self.assertEqual(result.message, "Only ASCII characters are allowed")

    def test_render_produces_image(self) -> None:
        result = render_barcode(
            BarcodeRequest(value="AS123", preset_id=DEFAULT_PRESET_ID)
        )
        self.assertGreater(result.pixel_width, 0)
        self.assertGreater(result.pixel_height, 0)
        self.assertEqual(result.image.size, (result.pixel_width, result.pixel_height))

    def test_render_warns_for_custom_colors(self) -> None:
        result = render_barcode(
            BarcodeRequest(
                value="BOX-2026-014",
                preset_id=DEFAULT_PRESET_ID,
                overrides={"foreground": "#004d40"},
            )
        )
        self.assertIn("Custom colors may reduce scan reliability", result.warnings)

    def test_build_default_filename_sanitizes_input(self) -> None:
        filename = build_default_filename("Box / 2026 : 014")
        self.assertEqual(filename, "barcode_Box_2026_014.png")

    def test_resolve_unique_path_appends_timestamp(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            original = Path(tmp_dir) / "barcode_test.png"
            original.touch()
            unique_path = resolve_unique_path(original)
            self.assertNotEqual(unique_path, original)
            self.assertEqual(unique_path.suffix, ".png")
            self.assertTrue(unique_path.name.startswith("barcode_test_"))


if __name__ == "__main__":
    unittest.main()
