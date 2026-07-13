class DecodingError(ValueError):
    pass


def decode(raw: bytes, source: str) -> str:
    """Decode as UTF-8 (BOM-tolerant); binary or badly-encoded input is rejected
    here rather than producing mojibake chunks downstream."""
    if b"\x00" in raw:
        raise DecodingError(f"{source}: binary content")
    try:
        return raw.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise DecodingError(f"{source}: not valid UTF-8 ({exc.reason})") from exc
