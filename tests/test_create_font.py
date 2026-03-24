#!/usr/bin/env python
"""Tests for create_font.py - SVG to TTF font generation."""

import json
import tempfile
from pathlib import Path
import pytest
from fontTools.ttLib import TTFont

# Import the functions to test
import sys
sys.path.insert(0, str(Path(__file__).parent.parent / "03-font-generation"))

from create_font import (
    load_svg_glyph,
    svg_path_to_contours,
    create_glyph_set,
    build_font,
    save_font,
)


class TestSVGPathParsing:
    """Test SVG path data parsing."""

    def test_svg_path_to_contours_simple_line(self):
        """Parse simple line path: M 100 200 L 150 250."""
        path_data = "M 100 200 L 150 250"
        contours = svg_path_to_contours(path_data)

        assert len(contours) == 1, "Should have one contour"
        assert len(contours[0]) == 2, "Contour should have 2 points"
        assert contours[0][0] == (100, 200)
        assert contours[0][1] == (150, 250)

    def test_svg_path_to_contours_multiple_segments(self):
        """Parse path with multiple line segments."""
        path_data = "M 100 200 L 150 250 L 200 300"
        contours = svg_path_to_contours(path_data)

        assert len(contours) == 1
        assert len(contours[0]) == 3
        assert contours[0] == [(100, 200), (150, 250), (200, 300)]

    def test_svg_path_to_contours_multiple_subpaths(self):
        """Parse path with multiple subpaths (multiple M commands)."""
        path_data = "M 100 200 L 150 250 M 300 400 L 350 450"
        contours = svg_path_to_contours(path_data)

        assert len(contours) == 2, "Should have two contours"
        assert contours[0] == [(100, 200), (150, 250)]
        assert contours[1] == [(300, 400), (350, 450)]

    def test_svg_path_to_contours_with_floats(self):
        """Parse path with floating-point coordinates."""
        path_data = "M 498.00 295.00 L 488.00 295.00 L 486.00 268.00"
        contours = svg_path_to_contours(path_data)

        assert len(contours) == 1
        assert len(contours[0]) == 3
        # Floats should be converted to ints
        assert contours[0][0] == (498, 295)
        assert contours[0][1] == (488, 295)
        assert contours[0][2] == (486, 268)

    def test_svg_path_to_contours_empty_string(self):
        """Parse empty path data."""
        contours = svg_path_to_contours("")
        assert contours == []

    def test_svg_path_to_contours_whitespace_handling(self):
        """Parse path with extra whitespace."""
        path_data = "M   100   200   L   150   250"
        contours = svg_path_to_contours(path_data)

        assert len(contours) == 1
        assert contours[0] == [(100, 200), (150, 250)]


class TestSVGGlyphLoading:
    """Test loading SVG glyph files."""

    def test_load_svg_glyph_valid_file(self):
        """Load a valid SVG glyph file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            svg_path = Path(tmpdir) / "test.svg"
            svg_content = '''<?xml version="1.0" encoding="UTF-8"?>
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1000 1000">
  <path d="M 100 200 L 150 250" />
</svg>'''
            svg_path.write_text(svg_content)

            contours = load_svg_glyph(svg_path)
            assert len(contours) == 1
            assert contours[0] == [(100, 200), (150, 250)]

    def test_load_svg_glyph_with_defs(self):
        """Load SVG with <defs> and styling (like from generate_svg.py)."""
        with tempfile.TemporaryDirectory() as tmpdir:
            svg_path = Path(tmpdir) / "test.svg"
            svg_content = '''<?xml version="1.0" encoding="UTF-8"?>
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1000 1000">
  <defs>
    <style type="text/css">
      path { fill: none; stroke: black; }
    </style>
  </defs>
  <path d="M 498 295 L 488 295 L 486 268" />
</svg>'''
            svg_path.write_text(svg_content)

            contours = load_svg_glyph(svg_path)
            assert len(contours) == 1
            assert len(contours[0]) == 3

    def test_load_svg_glyph_no_path(self):
        """Handle SVG with no path element."""
        with tempfile.TemporaryDirectory() as tmpdir:
            svg_path = Path(tmpdir) / "empty.svg"
            svg_content = '''<?xml version="1.0" encoding="UTF-8"?>
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1000 1000">
</svg>'''
            svg_path.write_text(svg_content)

            contours = load_svg_glyph(svg_path)
            assert contours == []


class TestGlyphSetCreation:
    """Test creating a glyph set from directory of SVG files."""

    def test_create_glyph_set_valid_files(self):
        """Load multiple SVG files into glyph set."""
        with tempfile.TemporaryDirectory() as tmpdir:
            glyphs_dir = Path(tmpdir)

            # Create test SVG files
            svg_c = glyphs_dir / "U+0043.svg"
            svg_c.write_text('''<?xml version="1.0" encoding="UTF-8"?>
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1000 1000">
  <path d="M 100 200 L 150 250" />
</svg>''')

            svg_p = glyphs_dir / "U+0050.svg"
            svg_p.write_text('''<?xml version="1.0" encoding="UTF-8"?>
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1000 1000">
  <path d="M 200 300 L 250 350" />
</svg>''')

            glyph_set = create_glyph_set(glyphs_dir)

            # Check that both glyphs were loaded
            assert "C" in glyph_set
            assert "P" in glyph_set
            assert len(glyph_set) == 2

    def test_create_glyph_set_unicode_mapping(self):
        """Verify correct mapping from Unicode hex to character."""
        with tempfile.TemporaryDirectory() as tmpdir:
            glyphs_dir = Path(tmpdir)

            # Create SVG with known Unicode
            svg_path = glyphs_dir / "U+0041.svg"  # 'A'
            svg_path.write_text('''<?xml version="1.0" encoding="UTF-8"?>
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1000 1000">
  <path d="M 100 200 L 150 250" />
</svg>''')

            glyph_set = create_glyph_set(glyphs_dir)

            assert "A" in glyph_set
            assert glyph_set["A"] == [[(100, 200), (150, 250)]]

    def test_create_glyph_set_empty_directory(self):
        """Handle empty directory gracefully."""
        with tempfile.TemporaryDirectory() as tmpdir:
            glyphs_dir = Path(tmpdir)
            glyph_set = create_glyph_set(glyphs_dir)
            assert glyph_set == {}


class TestFontBuilding:
    """Test building a font from glyph set."""

    def test_build_font_creates_ttfont(self):
        """Build font returns a valid TTFont object."""
        glyph_set = {
            "A": [[(100, 200), (150, 250)]],
            "B": [[(200, 300), (250, 350)]],
        }

        font = build_font(glyph_set)

        assert isinstance(font, TTFont)
        # Verify basic tables exist
        assert "cmap" in font
        assert "glyf" in font or "CFF " in font
        assert "name" in font

    def test_build_font_cmap_correctness(self):
        """Verify character map (cmap) is correct."""
        glyph_set = {"A": [[(100, 200), (150, 250)]]}
        font = build_font(glyph_set)

        cmap_table = font["cmap"]
        cmap = cmap_table.getBestCmap()

        # A = U+0041
        assert 0x0041 in cmap
        assert cmap[0x0041] == "A"

    def test_build_font_metrics(self):
        """Verify font metrics are set correctly."""
        glyph_set = {"A": [[(100, 200), (150, 250)]]}
        font = build_font(glyph_set)

        head = font["head"]
        assert head.unitsPerEm == 1000

        hhea = font["hhea"]
        assert hhea.ascent == 800
        assert hhea.descent == -200

    def test_build_font_name_table(self):
        """Verify font name table is configured."""
        glyph_set = {"A": [[(100, 200), (150, 250)]]}
        font = build_font(glyph_set)

        name_table = font["name"]
        # Get family name (nameID 1)
        family_name = None
        for record in name_table.names:
            if record.nameID == 1:
                family_name = record.toUnicode()
                break

        assert family_name == "Tava Beige"

    def test_build_font_includes_notdef(self):
        """Font should include .notdef glyph."""
        glyph_set = {"A": [[(100, 200), (150, 250)]]}
        font = build_font(glyph_set)

        cmap = font["cmap"].getBestCmap()
        # .notdef should be in glyph order but not in cmap
        assert ".notdef" in font.getGlyphOrder()


class TestFontSaving:
    """Test saving font to file."""

    def test_save_font_creates_file(self):
        """Save font creates a TTF file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = Path(tmpdir) / "test.ttf"

            glyph_set = {"A": [[(100, 200), (150, 250)]]}
            font = build_font(glyph_set)

            save_font(font, output_path)

            assert output_path.exists()
            assert output_path.suffix == ".ttf"

    def test_save_font_is_valid_ttf(self):
        """Saved font is a valid TTF that can be loaded."""
        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = Path(tmpdir) / "test.ttf"

            glyph_set = {"A": [[(100, 200), (150, 250)]]}
            font = build_font(glyph_set)
            save_font(font, output_path)

            # Verify it's loadable
            loaded_font = TTFont(output_path)
            assert "cmap" in loaded_font
            assert "glyf" in loaded_font or "CFF " in loaded_font

    def test_save_font_creates_parent_directories(self):
        """Save font creates parent directories if needed."""
        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = Path(tmpdir) / "subdir" / "nested" / "test.ttf"

            glyph_set = {"A": [[(100, 200), (150, 250)]]}
            font = build_font(glyph_set)

            save_font(font, output_path)

            assert output_path.exists()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
