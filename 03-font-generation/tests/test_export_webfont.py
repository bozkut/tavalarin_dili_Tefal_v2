"""Tests for export_webfont.py — TTF to WOFF2 conversion.

Uses TDD approach: tests were written before implementation.
External compress() function is mocked to isolate unit under test.
"""

import logging
import sys
from pathlib import Path
from unittest.mock import patch
import pytest

# Ensure the parent directory is on sys.path so we can import export_webfont
sys.path.insert(0, str(Path(__file__).parent.parent))

from export_webfont import get_file_size_kb, export_woff2


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def tmp_ttf(tmp_path):
    """Create a small fake TTF file (content doesn't matter for unit tests)."""
    ttf_file = tmp_path / "TestFont.ttf"
    # Write 10 240-byte fake content so size is exactly 10.0 KB
    ttf_file.write_bytes(b"X" * 10240)
    return ttf_file


@pytest.fixture
def tmp_woff2_path(tmp_path):
    """Return a path for a WOFF2 output that doesn't exist yet."""
    return tmp_path / "output" / "TestFont.woff2"


@pytest.fixture
def fake_compress_side_effect():
    def _compress(_in_path, out_path):
        Path(out_path).parent.mkdir(parents=True, exist_ok=True)
        Path(out_path).write_bytes(b"Y" * 5120)
    return _compress


# ---------------------------------------------------------------------------
# get_file_size_kb
# ---------------------------------------------------------------------------

class TestGetFileSizeKb:
    def test_returns_float(self, tmp_ttf):
        result = get_file_size_kb(tmp_ttf)
        assert isinstance(result, float)

    def test_correct_size(self, tmp_ttf):
        # File is 10 240 bytes == 10.0 KB
        assert get_file_size_kb(tmp_ttf) == pytest.approx(10.0, abs=0.01)

    def test_zero_byte_file(self, tmp_path):
        empty = tmp_path / "empty.ttf"
        empty.write_bytes(b"")
        assert get_file_size_kb(empty) == pytest.approx(0.0)

    def test_accepts_path_object(self, tmp_ttf):
        # Must accept a pathlib.Path (not just str)
        result = get_file_size_kb(Path(tmp_ttf))
        assert result > 0


# ---------------------------------------------------------------------------
# export_woff2 — happy path (compress mocked)
# ---------------------------------------------------------------------------

class TestExportWoff2:
    def test_calls_compress_with_string_paths(self, tmp_ttf, tmp_woff2_path, fake_compress_side_effect):
        """compress() must receive str arguments, not Path objects."""
        with patch("export_webfont.compress") as mock_compress:
            mock_compress.side_effect = fake_compress_side_effect

            export_woff2(tmp_ttf, tmp_woff2_path)

            mock_compress.assert_called_once_with(
                str(tmp_ttf), str(tmp_woff2_path)
            )

    def test_creates_output_directory(self, tmp_ttf, tmp_woff2_path, fake_compress_side_effect):
        """Output directory must be created if it doesn't exist."""
        assert not tmp_woff2_path.parent.exists()

        with patch("export_webfont.compress") as mock_compress:
            mock_compress.side_effect = fake_compress_side_effect

            export_woff2(tmp_ttf, tmp_woff2_path)

        assert tmp_woff2_path.parent.exists()

    def test_output_file_created(self, tmp_ttf, tmp_woff2_path, fake_compress_side_effect):
        """WOFF2 output file must exist after successful conversion."""
        with patch("export_webfont.compress") as mock_compress:
            mock_compress.side_effect = fake_compress_side_effect

            export_woff2(tmp_ttf, tmp_woff2_path)

        assert tmp_woff2_path.exists()

    def test_logs_compression_stats(self, tmp_ttf, tmp_woff2_path, caplog, fake_compress_side_effect):
        """Compression ratio must appear in log output."""
        with patch("export_webfont.compress") as mock_compress:
            mock_compress.side_effect = fake_compress_side_effect

            with caplog.at_level(logging.INFO, logger="export_webfont"):
                export_woff2(tmp_ttf, tmp_woff2_path)

        # At least one log record must mention "Compression" or "reduction"
        messages = " ".join(caplog.messages)
        assert "Compression" in messages or "reduction" in messages

    def test_logs_input_path(self, tmp_ttf, tmp_woff2_path, caplog, fake_compress_side_effect):
        with patch("export_webfont.compress") as mock_compress:
            mock_compress.side_effect = fake_compress_side_effect

            with caplog.at_level(logging.INFO, logger="export_webfont"):
                export_woff2(tmp_ttf, tmp_woff2_path)

        messages = " ".join(caplog.messages)
        assert tmp_ttf.name in messages

    def test_logs_output_path(self, tmp_ttf, tmp_woff2_path, caplog, fake_compress_side_effect):
        with patch("export_webfont.compress") as mock_compress:
            mock_compress.side_effect = fake_compress_side_effect

            with caplog.at_level(logging.INFO, logger="export_webfont"):
                export_woff2(tmp_ttf, tmp_woff2_path)

        messages = " ".join(caplog.messages)
        assert tmp_woff2_path.name in messages


# ---------------------------------------------------------------------------
# export_woff2 — error handling
# ---------------------------------------------------------------------------

class TestExportWoff2ErrorHandling:
    def test_missing_input_file_exits(self, tmp_path, tmp_woff2_path):
        """sys.exit(1) when input TTF does not exist."""
        missing = tmp_path / "nonexistent.ttf"

        with pytest.raises(SystemExit) as exc_info:
            export_woff2(missing, tmp_woff2_path)

        assert exc_info.value.code == 1

    def test_compress_failure_exits(self, tmp_ttf, tmp_woff2_path):
        """sys.exit(1) when compress() raises an exception."""
        with patch("export_webfont.compress", side_effect=Exception("Brotli error")):
            with pytest.raises(SystemExit) as exc_info:
                export_woff2(tmp_ttf, tmp_woff2_path)

        assert exc_info.value.code == 1

    def test_compress_failure_logs_error(self, tmp_ttf, tmp_woff2_path, caplog):
        with patch("export_webfont.compress", side_effect=Exception("Brotli error")):
            with caplog.at_level(logging.ERROR, logger="export_webfont"):
                with pytest.raises(SystemExit):
                    export_woff2(tmp_ttf, tmp_woff2_path)

        messages = " ".join(caplog.messages)
        assert "error" in messages.lower() or "Brotli error" in messages


# ---------------------------------------------------------------------------
# CLI (Click) interface tests
# ---------------------------------------------------------------------------

class TestCLI:
    def test_cli_requires_input(self):
        from click.testing import CliRunner
        from export_webfont import main

        runner = CliRunner()
        result = runner.invoke(main, ["--output", "out.woff2"])
        assert result.exit_code != 0

    def test_cli_requires_output(self, tmp_ttf):
        from click.testing import CliRunner
        from export_webfont import main

        runner = CliRunner()
        result = runner.invoke(main, ["--input", str(tmp_ttf)])
        assert result.exit_code != 0

    def test_cli_missing_input_file(self, tmp_path):
        """CLI exits with non-zero when input file doesn't exist."""
        from click.testing import CliRunner
        from export_webfont import main

        runner = CliRunner()
        missing = tmp_path / "no.ttf"
        out = tmp_path / "out.woff2"
        result = runner.invoke(main, ["--input", str(missing), "--output", str(out)])
        assert result.exit_code != 0

    def test_cli_successful_conversion(self, tmp_ttf, tmp_woff2_path, fake_compress_side_effect):
        """CLI exits 0 on successful conversion."""
        from click.testing import CliRunner
        from export_webfont import main

        with patch("export_webfont.compress") as mock_compress:
            mock_compress.side_effect = fake_compress_side_effect

            runner = CliRunner()
            result = runner.invoke(
                main,
                ["--input", str(tmp_ttf), "--output", str(tmp_woff2_path)],
            )

        assert result.exit_code == 0
