"""Sign a Leadroom installer for the in-app updater.

Leadroom has no code-signing certificate, so Windows does not vouch for an installer the app
downloads. This Ed25519 signature does instead: the app installs an update only when its
``.sig`` file verifies against the public key built into it (``app/updater.py``).

The private key never enters the repository. It is kept in ``%USERPROFILE%\\.leadroom``,
encrypted with Windows DPAPI for this Windows account only. Without it no further update can
reach installed copies, so keep the text ``export`` prints somewhere safe (a password
manager) and bring it back on another computer with ``import``.

Usage (with the build virtual environment's Python):
    python scripts/sign_update.py keygen            make the key, once
    python scripts/sign_update.py public            print the public key for app/updater.py
    python scripts/sign_update.py sign FILE         write FILE.sig
    python scripts/sign_update.py export            print the private key, for a backup
    python scripts/sign_update.py import            read a backed-up private key from stdin

``--key-file PATH`` uses a plain, unencrypted key file instead. It exists for throwaway test
keys (the clean-machine workflow makes one per run) and must never hold the release key.
"""

from __future__ import annotations

import argparse
import base64
import ctypes
import os
import sys
from ctypes import wintypes
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from cryptography.hazmat.primitives import serialization  # noqa: E402
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey  # noqa: E402

from app.updater import signed_message  # noqa: E402

KEY_FILE = Path(os.environ.get("USERPROFILE", str(Path.home()))) / ".leadroom" / "update-signing.key"
# Extra entropy so the protected blob is only usable by this tool.
PURPOSE = b"leadroom-update-signing"


class _Blob(ctypes.Structure):
    _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_char))]


def _blob(data: bytes) -> _Blob:
    buffer = ctypes.create_string_buffer(data, len(data))
    return _Blob(len(data), ctypes.cast(buffer, ctypes.POINTER(ctypes.c_char)))


def _dpapi(data: bytes, protect: bool) -> bytes:
    if os.name != "nt":
        raise SystemExit("The release key is protected with Windows DPAPI; use Windows or --key-file.")
    crypt32 = ctypes.windll.crypt32
    output = _Blob()
    function = crypt32.CryptProtectData if protect else crypt32.CryptUnprotectData
    ok = function(
        ctypes.byref(_blob(data)), None, ctypes.byref(_blob(PURPOSE)), None, None, 0, ctypes.byref(output)
    )
    if not ok:
        raise SystemExit(f"Windows could not {'protect' if protect else 'read'} the key (DPAPI error).")
    try:
        return ctypes.string_at(output.pbData, output.cbData)
    finally:
        ctypes.windll.kernel32.LocalFree(output.pbData)


def _load(key_file: Path | None) -> Ed25519PrivateKey:
    if key_file:
        seed = base64.b64decode(key_file.read_text(encoding="ascii").strip())
    else:
        if not KEY_FILE.exists():
            raise SystemExit("No signing key. Make one with `keygen` or restore one with `import`.")
        seed = _dpapi(KEY_FILE.read_bytes(), protect=False)
    return Ed25519PrivateKey.from_private_bytes(seed)


def _store(seed: bytes, key_file: Path | None) -> None:
    if key_file:
        key_file.parent.mkdir(parents=True, exist_ok=True)
        key_file.write_text(base64.b64encode(seed).decode("ascii"), encoding="ascii")
        return
    KEY_FILE.parent.mkdir(parents=True, exist_ok=True)
    KEY_FILE.write_bytes(_dpapi(seed, protect=True))


def _seed(key: Ed25519PrivateKey) -> bytes:
    return key.private_bytes(
        serialization.Encoding.Raw, serialization.PrivateFormat.Raw, serialization.NoEncryption()
    )


def public_key_text(key: Ed25519PrivateKey) -> str:
    raw = key.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)
    return base64.b64encode(raw).decode("ascii")


def sign_file(path: Path, key: Ed25519PrivateKey) -> Path:
    signature = key.sign(signed_message(path))
    target = path.with_name(path.name + ".sig")
    target.write_text(base64.b64encode(signature).decode("ascii") + "\n", encoding="ascii")
    return target


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--key-file", type=Path, help="plain key file, for throwaway test keys only")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("keygen")
    commands.add_parser("public")
    sign = commands.add_parser("sign")
    sign.add_argument("file", type=Path)
    commands.add_parser("export")
    commands.add_parser("import")
    args = parser.parse_args(argv)
    key_file: Path | None = args.key_file

    if args.command == "keygen":
        target = key_file or KEY_FILE
        if target.exists():
            raise SystemExit(f"A key already exists in {target}; it is not replaced.")
        key = Ed25519PrivateKey.generate()
        _store(_seed(key), key_file)
        print(f"Key made and kept in {target}")
        print(f"Public key: {public_key_text(key)}")
        if not key_file:
            print("Back it up now with `export`.")
    elif args.command == "public":
        print(public_key_text(_load(key_file)))
    elif args.command == "sign":
        if not args.file.is_file():
            raise SystemExit(f"No file at {args.file}")
        print(f"Wrote {sign_file(args.file, _load(key_file))}")
    elif args.command == "export":
        print(base64.b64encode(_seed(_load(key_file))).decode("ascii"))
    elif args.command == "import":
        target = key_file or KEY_FILE
        if target.exists():
            raise SystemExit(f"A key already exists in {target}; it is not replaced.")
        seed = base64.b64decode(sys.stdin.readline().strip())
        key = Ed25519PrivateKey.from_private_bytes(seed)
        _store(seed, key_file)
        print(f"Key restored to {target}; public key {public_key_text(key)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
