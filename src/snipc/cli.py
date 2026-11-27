import io
import platform
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Optional

import typer
from PIL import Image, ImageColor, ImageDraw, ImageFilter, ImageFont
from pygments import highlight
from pygments.formatters import ImageFormatter
from pygments.lexers import TextLexer, get_lexer_for_filename
from pygments.styles import get_all_styles
from pygments.util import ClassNotFound

app = typer.Typer(
    help="Generate aesthetic code snippet cards straight from your terminal.",
    no_args_is_help=True,
)

GRADIENTS: dict[str, tuple[str, str]] = {
    "ocean": ("#2193b0", "#6dd5ed"),
    "sunset": ("#ee0979", "#ff6a00"),
    "emerald": ("#11998e", "#38ef7d"),
    "cyberpunk": ("#8e2de2", "#4a00e0"),
    "peach": ("#ff9a9e", "#fecfef"),
    "midnight": ("#232526", "#414345"),
}


def create_background(width: int, height: int, bg: str) -> Image.Image:
    """Create a solid color or vertical linear gradient background."""
    if bg.lower() in GRADIENTS:
        c1, c2 = GRADIENTS[bg.lower()]
        r1, g1, b1 = ImageColor.getrgb(c1)
        r2, g2, b2 = ImageColor.getrgb(c2)

        base = Image.new("RGBA", (width, height))
        draw = ImageDraw.Draw(base)
        for y in range(height):
            ratio = y / max(height - 1, 1)
            r = int(r1 + (r2 - r1) * ratio)
            g = int(g1 + (g2 - g1) * ratio)
            b = int(b1 + (b2 - b1) * ratio)
            draw.line([(0, y), (width, y)], fill=(r, g, b, 255))
        return base

    try:
        return Image.new("RGBA", (width, height), bg)
    except ValueError:
        typer.secho(f"Unknown color or gradient: {bg}", fg=typer.colors.RED)
        raise typer.Exit(code=1)


def extract_lines(code: str, lines_range: Optional[str]) -> str:
    """Slice code by line range (e.g., '10:25')."""
    if not lines_range:
        return code
    try:
        start_str, end_str = lines_range.split(":")
        lines = code.splitlines()
        start = int(start_str) - 1 if start_str else 0
        end = int(end_str) if end_str else len(lines)
        return "\n".join(lines[start:end])
    except ValueError:
        typer.secho("Invalid --lines format. Use START:END (e.g., 10:25)", fg=typer.colors.RED)
        raise typer.Exit(code=1)


def copy_image_to_clipboard(image_path: Path) -> bool:
    """Copy PNG image to system clipboard (Linux Wayland/X11, macOS, Windows)."""
    system = platform.system()
    abs_path = str(image_path.resolve())

    try:
        if system == "Linux":
            if shutil.which("wl-copy"):
                with open(abs_path, "rb") as f:
                    subprocess.run(["wl-copy", "--type", "image/png"], stdin=f, check=True)
                return True
            if shutil.which("xclip"):
                subprocess.run(
                    ["xclip", "-selection", "clipboard", "-t", "image/png", "-i", abs_path],
                    check=True,
                )
                return True
        elif system == "Darwin":
            script = f'set the clipboard to (read (POSIX file "{abs_path}") as «class PNGf»)'
            subprocess.run(["osascript", "-e", script], check=True)
            return True
        elif system == "Windows":
            ps_cmd = (
                f"Add-Type -AssemblyName System.Windows.Forms; "
                f"[System.Windows.Forms.Clipboard]::SetImage([System.Drawing.Image]::FromFile('{abs_path}'))"
            )
            subprocess.run(["powershell", "-Command", ps_cmd], check=True)
            return True
    except subprocess.CalledProcessError:
        return False

    return False


def add_window_frame(
    code_img: Image.Image,
    bg: str = "cyberpunk",
    title: Optional[str] = None,
) -> Image.Image:
    padding = 55
    header_height = 42
    radius = 14

    window_bg = code_img.getpixel((0, 0))
    win_w = max(code_img.width + 40, 260)
    win_h = code_img.height + header_height + 20

    total_w = win_w + padding * 2
    total_h = win_h + padding * 2

    canvas = create_background(total_w, total_h, bg)

    # Drop shadow
    shadow = Image.new("RGBA", (total_w, total_h), (0, 0, 0, 0))
    shadow_draw = ImageDraw.Draw(shadow)
    shadow_box = [padding, padding + 14, padding + win_w, padding + win_h + 14]
    shadow_draw.rounded_rectangle(shadow_box, radius=radius, fill=(0, 0, 0, 120))
    shadow = shadow.filter(ImageFilter.GaussianBlur(radius=20))
    canvas = Image.alpha_composite(canvas, shadow)

    # Editor window
    draw = ImageDraw.Draw(canvas)
    win_box = [padding, padding, padding + win_w, padding + win_h]
    draw.rounded_rectangle(win_box, radius=radius, fill=window_bg)

    # macOS traffic lights
    colors = ["#ff5f56", "#ffbd2e", "#27c93f"]
    for i, color in enumerate(colors):
        cx = padding + 22 + i * 22
        cy = padding + 21
        draw.ellipse([cx - 6, cy - 6, cx + 6, cy + 6], fill=color)

    # File title
    if title:
        brightness = sum(window_bg[:3]) / 3
        text_color = (180, 180, 180, 220) if brightness < 128 else (90, 90, 90, 220)
        font = ImageFont.load_default()
        bbox = draw.textbbox((0, 0), title, font=font)
        text_w = bbox[2] - bbox[0]
        text_x = padding + (win_w - text_w) // 2
        text_y = padding + 15
        draw.text((text_x, text_y), title, fill=text_color, font=font)

    canvas.paste(code_img, (padding + 20, padding + header_height))
    return canvas


def list_themes_callback(value: bool):
    if value:
        themes = ", ".join(sorted(get_all_styles()))
        typer.echo(f"Available themes:\n{themes}\n")
        typer.echo(f"Available gradients:\n{', '.join(GRADIENTS.keys())}")
        raise typer.Exit()


@app.command()
def render(
    file_path: Path = typer.Argument(..., exists=True, help="Path to the source code file"),
    output: Optional[Path] = typer.Option(None, "--out", "-o", help="Output PNG file path (defaults to snippet.png)"),
    theme: str = typer.Option("dracula", "--theme", "-t", help="Syntax highlighting theme"),
    bg: str = typer.Option("cyberpunk", "--bg", help="HEX color or gradient (ocean, sunset, emerald, cyberpunk, peach, midnight)"),
    lines: Optional[str] = typer.Option(None, "--lines", "-l", help="Line range to capture (e.g., 1:25)"),
    line_numbers: bool = typer.Option(False, "--numbers", "-n", help="Show line numbers"),
    no_title: bool = typer.Option(False, "--no-title", help="Hide filename in the window header"),
    copy: bool = typer.Option(False, "--copy", "-c", help="Copy image directly to clipboard"),
    font: Optional[str] = typer.Option(None, "--font", "-f", help="System font family name (e.g., 'JetBrains Mono')"),
    list_themes: Optional[bool] = typer.Option(
        None, "--list-themes", callback=list_themes_callback, is_eager=True, help="List all available themes and gradients"
    ),
):
    """Render a code file into an aesthetic PNG image."""
    raw_code = file_path.read_text(encoding="utf-8")
    code = extract_lines(raw_code, lines)

    try:
        lexer = get_lexer_for_filename(file_path.name)
    except ClassNotFound:
        lexer = TextLexer()

    formatter_kwargs = {
        "style": theme,
        "line_numbers": line_numbers,
        "font_size": 20,
        "image_pad": 10,
    }
    if font:
        formatter_kwargs["font_name"] = font

    try:
        formatter = ImageFormatter(**formatter_kwargs)
    except ClassNotFound:
        typer.secho(f"Theme '{theme}' not found. Run --list-themes to see available options.", fg=typer.colors.RED)
        raise typer.Exit(code=1)

    img_bytes = highlight(code, lexer, formatter)
    code_img = Image.open(io.BytesIO(img_bytes)).convert("RGBA")

    title = None if no_title else file_path.name
    final_img = add_window_frame(code_img, bg=bg, title=title)

    # Save to temporary file if --copy is passed without explicit --out
    if copy and output is None:
        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
            tmp_path = Path(tmp.name)
        final_img.save(tmp_path)
        if copy_image_to_clipboard(tmp_path):
            typer.secho("Copied snippet image to clipboard!", fg=typer.colors.CYAN)
        else:
            typer.secho("Clipboard copy failed (install wl-clipboard or xclip on Linux).", fg=typer.colors.YELLOW)
        tmp_path.unlink(missing_ok=True)
        return

    target_path = output or Path("snippet.png")
    final_img.save(target_path)
    typer.secho(f"Saved snippet to {target_path}", fg=typer.colors.GREEN)

    if copy:
        if copy_image_to_clipboard(target_path):
            typer.secho("Copied snippet image to clipboard!", fg=typer.colors.CYAN)
        else:
            typer.secho("Clipboard copy failed (install wl-clipboard or xclip on Linux).", fg=typer.colors.YELLOW)


if __name__ == "__main__":
    app()

