from base64 import urlsafe_b64decode


def b64_decode(s: str) -> bytes:
    padded = s + '=' * (-len(s) % 4)
    return urlsafe_b64decode(padded)


def b64_encode(data: bytes) -> str:
    from base64 import urlsafe_b64encode

    return urlsafe_b64encode(data).rstrip(b'=').decode('ascii')
