import pytest

from app.youtube import YouTubeError, extract_video_id


@pytest.mark.parametrize(
    ("url", "expected"),
    [
        ("https://www.youtube.com/watch?v=dQw4w9WgXcQ", "dQw4w9WgXcQ"),
        ("https://youtu.be/dQw4w9WgXcQ?t=20", "dQw4w9WgXcQ"),
        ("https://youtube.com/shorts/dQw4w9WgXcQ", "dQw4w9WgXcQ"),
        ("https://youtube.com/embed/dQw4w9WgXcQ", "dQw4w9WgXcQ"),
    ],
)
def test_extract_video_id(url: str, expected: str) -> None:
    assert extract_video_id(url) == expected


@pytest.mark.parametrize(
    "url",
    [
        "https://example.com/watch?v=dQw4w9WgXcQ",
        "https://youtube.com/playlist?list=PL123",
        "https://youtube.com/watch?v=bad$id",
    ],
)
def test_rejects_unsupported_urls(url: str) -> None:
    with pytest.raises(YouTubeError):
        extract_video_id(url)
