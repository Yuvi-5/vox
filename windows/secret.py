"""Protects secrets stored in config.json with the Windows login (DPAPI).

A protected value looks like ``dpapi:<base64>`` and can only be opened by the same Windows user on the same PC,
so a copied or backed-up config.json no longer reveals the API key. Plain values are still read, and are
protected the next time the config is saved. Off Windows nothing is encrypted.
"""
import base64
import ctypes
import logging
import sys
from ctypes import wintypes

log = logging.getLogger("vox.secret")
PREFIX = "dpapi:"


class _Blob(ctypes.Structure):
    _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_char))]


def _win_call(data, protect):
    crypt32, kernel32 = ctypes.windll.crypt32, ctypes.windll.kernel32
    fn = crypt32.CryptProtectData if protect else crypt32.CryptUnprotectData
    fn.argtypes = [ctypes.POINTER(_Blob), ctypes.c_void_p, ctypes.POINTER(_Blob), ctypes.c_void_p,
                   ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(_Blob)]
    fn.restype = wintypes.BOOL
    kernel32.LocalFree.argtypes = [ctypes.c_void_p]
    buf = ctypes.create_string_buffer(data, len(data))
    src = _Blob(len(data), ctypes.cast(buf, ctypes.POINTER(ctypes.c_char)))
    out = _Blob()
    if not fn(ctypes.byref(src), None, None, None, None, 0, ctypes.byref(out)):
        raise OSError(ctypes.GetLastError(), "DPAPI call failed")
    try:
        return ctypes.string_at(out.pbData, out.cbData)
    finally:
        kernel32.LocalFree(out.pbData)


# (encrypt, decrypt) on Windows, None elsewhere. Tests replace this with a reversible fake.
_backend = (lambda b: _win_call(b, True), lambda b: _win_call(b, False)) if sys.platform == "win32" else None


def is_protected(value):
    return isinstance(value, str) and value.startswith(PREFIX)


def available():
    return _backend is not None


def protect(text):
    """Returns ``dpapi:...`` for a non-empty secret, or the text unchanged when it cannot be protected."""
    if not text or is_protected(text) or _backend is None:
        return text
    try:
        return PREFIX + base64.b64encode(_backend[0](text.encode("utf-8"))).decode("ascii")
    except Exception:
        log.exception("could not protect a secret; leaving it as plain text")
        return text


def unprotect(value):
    """Plain text of a secret. Empty when a protected value cannot be opened (other user or other PC)."""
    if not is_protected(value):
        return value
    if _backend is None:
        return ""
    try:
        return _backend[1](base64.b64decode(value[len(PREFIX):])).decode("utf-8")
    except Exception:
        log.warning("could not open a protected secret (different Windows user or PC?)")
        return ""
