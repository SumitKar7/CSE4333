# app/cli.py
import click
from pathlib import Path
from app.converter import convert_to_audio, ConversionError

@click.command()
@click.argument("input_file", type=click.Path(exists=True))
@click.option("--output", "-o", default=None, help="Output audio file path (optional).")
@click.option("--codec", default="mp3", type=click.Choice(["mp3", "aac", "copy"]), help="Audio codec/output format.")
@click.option("--quality", default=2, help="Quality for mp3 (0 best .. 9 worst).")
def cli(input_file, output, codec, quality):
    """Convert a video file to audio using ffmpeg."""
    input_path = Path(input_file)
    if output:
        output_path = Path(output)
    else:
        # default output in same dir with .mp3 or .aac
        ext = "mp3" if codec == "mp3" else "m4a"
        output_path = input_path.with_suffix(f".{ext}")

    try:
        code, out = convert_to_audio(str(input_path), str(output_path), codec=codec, quality=quality)
        click.secho(f"Conversion succeeded -> {out}", fg="green")
    except ConversionError as e:
        click.secho(f"Conversion failed: {e}", fg="red")
        raise SystemExit(1)

if __name__ == "__main__":
    cli()
