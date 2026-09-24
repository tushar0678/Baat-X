from __future__ import annotations

import pytest

from app.config.settings import get_settings
from app.core.errors import AudioTooLargeError, UnsupportedAudioError
from app.services.audio.validator import validate_audio

SAMPLES = {
    "mp3": b"ID3\x04\x00\x00\x00" + b"\x00" * 64,
    "wav": b"RIFF\x24\x00\x00\x00WAVEfmt " + b"\x00" * 32,
    "ogg": b"OggS\x00\x02" + b"\x00" * 64,
    "amr": b"#!AMR\n" + b"\x00" * 64,
    "m4a": b"\x00\x00\x00\x20ftypM4A " + b"\x00" * 64,
}


@pytest.mark.parametrize("extension", sorted(SAMPLES))
def test_supported_formats_are_accepted(extension: str) -> None:
    result = validate_audio(
        filename=f"recording.{extension}",
        declared_content_type=None,
        data=SAMPLES[extension],
        settings=get_settings(),
    )
    assert result.extension == extension


def test_executable_disguised_as_audio_is_rejected() -> None:
    with pytest.raises(UnsupportedAudioError):
        validate_audio(
            filename="malware.mp3",
            declared_content_type="audio/mpeg",
            data=b"MZ\x90\x00\x03" + b"\x00" * 64,  # PE header
            settings=get_settings(),
        )


def test_unsupported_extension_message_lists_formats() -> None:
    with pytest.raises(UnsupportedAudioError) as exc:
        validate_audio(
            filename="notes.txt",
            declared_content_type="text/plain",
            data=b"just some text",
            settings=get_settings(),
        )
    assert "MP3, M4A, WAV, AAC, AMR, or OGG" in exc.value.user_message


def test_oversized_upload_is_rejected() -> None:
    settings = get_settings()
    with pytest.raises(AudioTooLargeError):
        validate_audio(
            filename="huge.mp3",
            declared_content_type="audio/mpeg",
            data=b"ID3" + b"\x00" * (settings.audio_max_bytes + 1),
            settings=settings,
        )


def test_empty_upload_is_rejected() -> None:
    with pytest.raises(UnsupportedAudioError):
        validate_audio(
            filename="empty.mp3",
            declared_content_type="audio/mpeg",
            data=b"",
            settings=get_settings(),
        )
