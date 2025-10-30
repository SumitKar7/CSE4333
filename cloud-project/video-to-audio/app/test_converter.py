# tests/test_converter.py
import os
from pathlib import Path
import pytest
from app.converter import convert_to_audio, ConversionError

SAMPLE_DIR = Path(__file__).resolve().parent.parent / "sample_videos"
SAMPLE_VIDEO = SAMPLE_DIR / "sample.mp4"

@pytest.mark.skipif(not SAMPLE_VIDEO.exists(), reason="sample video missing in sample_videos/")
def test_convert_mp3(tmp_path):
    out = tmp_path / "out.mp3"
    code, path = convert_to_audio(str(SAMPLE_VIDEO), str(out), codec="mp3", quality=5)
    assert code == 0
    assert Path(path).exists()
    assert Path(path).stat().st_size > 0

def test_missing_input():
    with pytest.raises(ConversionError):
        convert_to_audio("nonexistent_file.mp4", "/tmp/out.mp3")
