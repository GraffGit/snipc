from typer.testing import CliRunner
from snipc.cli import app, extract_lines


runner = CliRunner()


def test_extract_lines():
    sample = "line1\nline2\nline3\nline4"
    assert extract_lines(sample, "2:3") == "line2\nline3"
    assert extract_lines(sample, None) == sample


def test_list_themes():
    result = runner.invoke(app, ["--list-themes"])
    assert result.exit_code == 0
    assert "dracula" in result.stdout
    assert "cyberpunk" in result.stdout


def test_render_creates_png(tmp_path):
    code_file = tmp_path / "hello.py"
    code_file.write_text("print('Hello, Arch Linux!')\n", encoding="utf-8")
    out_img = tmp_path / "out.png"

    result = runner.invoke(app, [str(code_file), "-o", str(out_img), "--bg", "sunset"])
    assert result.exit_code == 0
    assert out_img.exists()
    assert out_img.stat().st_size > 0
