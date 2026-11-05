"""Protect local credentials with the current Windows user's DPAPI profile."""

from __future__ import annotations

import base64
import ctypes
import os
from ctypes import POINTER, Structure, byref, c_ubyte, c_void_p
from ctypes.wintypes import DWORD

_PREFIX = "dpapi:"


def is_protected_secret(value: str) -> bool:
    return value.startswith(_PREFIX)


class _DataBlob(Structure):
    _fields_ = [("cbData", DWORD), ("pbData", POINTER(c_ubyte))]


def _dpapi(value: bytes, protect: bool) -> bytes:
    if os.name != "nt":
        raise OSError("DPAPI esta disponivel somente no Windows.")

    source_buffer = (c_ubyte * len(value)).from_buffer_copy(value)
    source = _DataBlob(len(value), ctypes.cast(source_buffer, POINTER(c_ubyte)))
    destination = _DataBlob()
    crypt32 = ctypes.WinDLL("crypt32", use_last_error=True)
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    if protect:
        operation = crypt32.CryptProtectData
        operation.argtypes = [
            POINTER(_DataBlob), ctypes.c_wchar_p, POINTER(_DataBlob), c_void_p,
            c_void_p, DWORD, POINTER(_DataBlob),
        ]
        operation.restype = ctypes.c_int
        succeeded = operation(
            byref(source), "Altair credential", None, None, None, 0,
            byref(destination),
        )
    else:
        operation = crypt32.CryptUnprotectData
        operation.argtypes = [
            POINTER(_DataBlob), POINTER(ctypes.c_wchar_p), POINTER(_DataBlob),
            c_void_p, c_void_p, DWORD, POINTER(_DataBlob),
        ]
        operation.restype = ctypes.c_int
        description = ctypes.c_wchar_p()
        succeeded = operation(
            byref(source), byref(description), None, None, None, 0,
            byref(destination),
        )
    if not succeeded:
        raise ctypes.WinError(ctypes.get_last_error())

    try:
        return ctypes.string_at(destination.pbData, destination.cbData)
    finally:
        kernel32.LocalFree.argtypes = [c_void_p]
        kernel32.LocalFree.restype = c_void_p
        kernel32.LocalFree(destination.pbData)


def protect_secret(value: str) -> str:
    """Return a DPAPI-protected representation on Windows; leave dev values alone."""
    if not value or value.startswith(_PREFIX) or os.name != "nt":
        return value
    ciphertext = _dpapi(value.encode("utf-8"), protect=True)
    return _PREFIX + base64.b64encode(ciphertext).decode("ascii")


def unprotect_secret(value: str) -> str:
    """Decode DPAPI values and pass through older plaintext configuration values."""
    if not value.startswith(_PREFIX):
        return value
    try:
        plaintext = _dpapi(base64.b64decode(value[len(_PREFIX):]), protect=False)
        return plaintext.decode("utf-8")
    except Exception:
        # If the Windows user profile changed, don't crash startup; the user can
        # replace the credential in settings.
        return ""


def read_secret_file(path: str) -> str:
    try:
        with open(path, encoding="utf-8") as secret_file:
            value = secret_file.read().strip()
        plaintext = unprotect_secret(value)
        protected = protect_secret(plaintext)
        if plaintext and not is_protected_secret(value) and protected != value:
            with open(path, "w", encoding="utf-8") as secret_file:
                secret_file.write(protected)
        return plaintext
    except Exception:
        return ""
