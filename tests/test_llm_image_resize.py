import base64
import io

from PIL import Image

from transcript_pipeline.llm.openai_compatible import _MAX_IMAGE_DIMENSION, _encode_image_b64


def _make_image(path, size, fmt="PNG"):
    img = Image.new("RGB", size, color=(10, 20, 30))
    img.save(path, format=fmt)


def test_small_image_sent_unmodified(tmp_path):
    path = tmp_path / "small.png"
    _make_image(path, (200, 150))
    b64, mime = _encode_image_b64(path)
    assert mime == "png"
    assert base64.b64decode(b64) == path.read_bytes()


def test_large_image_is_downscaled(tmp_path):
    path = tmp_path / "huge.png"
    _make_image(path, (4000, 3000))
    b64, mime = _encode_image_b64(path)
    assert mime == "jpeg"

    decoded = base64.b64decode(b64)
    assert len(decoded) < path.stat().st_size

    resized = Image.open(io.BytesIO(decoded))
    assert max(resized.size) <= _MAX_IMAGE_DIMENSION


def test_downscaled_image_preserves_aspect_ratio(tmp_path):
    path = tmp_path / "wide.png"
    _make_image(path, (4000, 1000))  # 4:1 aspect ratio
    b64, _ = _encode_image_b64(path)
    resized = Image.open(io.BytesIO(base64.b64decode(b64)))
    ratio = resized.size[0] / resized.size[1]
    assert abs(ratio - 4.0) < 0.05


def test_image_exactly_at_limit_not_downscaled(tmp_path):
    path = tmp_path / "exact.png"
    _make_image(path, (_MAX_IMAGE_DIMENSION, 500))
    b64, mime = _encode_image_b64(path)
    assert mime == "png"
    assert base64.b64decode(b64) == path.read_bytes()
