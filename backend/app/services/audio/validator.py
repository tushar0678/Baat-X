"""Upload validation: extension, declared MIME type, size and magic bytes.

Trusting the client's ``Content-Type`` alone is how malicious uploads get in, so
we also sniff the container signature.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.config.settings import Settings
from app.core.errors import AudioTooLargeError, UnsupportedAudioError

EXTENSION_MIME: dict[str, str] = {
    "mp3": "audio/mpeg",
    "m4a": "audio/mp4",
    "wav": "audio/wav",
    "aac": "audio/aac",
    "amr": "audio/amr",
    "ogg": "audio/ogg",
}

# (offset, signature) pairs that identify each supported container.
_MAGIC: dict[str, list[tuple[int, bytes]]] = {
    "mp3": [(0, b"ID3"), (0, b"\xff\xfb"), (0, b"\xff\xf3"), (0, b"\xff\xf2"), (0, b"\xff\xfa")],
    "m4a": [(4, b"ftyp")],
    "wav": [(0, b"RIFF")],
    "aac": [(0, b"\xff\xf1"), (0, b"\xff\xf9"), (0, b"ADIF")],
    "amr": [(0, b"#!AMR")],
    "ogg": [(0, b"OggS")],
}


@dataclass(slots=True)
class ValidatedAudio:
    extension: str
    content_type: str
    size_bytes: int


def _sniff(head: bytes) -> str | None:
    for extension, signatures in _MAGIC.items():
        for offset, signature in signatures:
            if head[offset : offset + len(signature)] == signature:
                return extension
    return None


def validate_audio(
    *,
    filename: str | None,
    declared_content_type: str | None,
    data: bytes,
    settings: Settings,
) -> ValidatedAudio:
    size = len(data)
    if size == 0:
        raise UnsupportedAudioError(
            "empty upload", user_message="That file appears to be empty. Please try again."
        )
    if size > settings.audio_max_bytes:
        raise AudioTooLargeError(f"{size} bytes exceeds limit")

    sniffed = _sniff(data[:32])
    if sniffed is None:
        # The declared extension is not enough - the container signature must match
        # one we support, otherwise a renamed executable would sail through.
        raise UnsupportedAudioError("unrecognised audio container")

    if sniffed not in settings.audio_allowed_extensions:
        raise UnsupportedAudioError(f"extension {sniffed} not allowed")

    return ValidatedAudio(
        extension=sniffed, content_type=EXTENSION_MIME[sniffed], size_bytes=size
    )
