import argparse
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

NOTE_BLOCK_RE = re.compile(r"(/\*\* Encrypt[^\n]*\n)(.*?)(\n\*\*/)", re.DOTALL)
CMS_MARKER = "-----BEGIN CMS-----"

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")


def repo_path(value: str) -> Path:
    path = Path(value)
    if path.is_absolute():
        return path
    return Path.cwd() / path


def key_paths(key_dir: str) -> dict[str, Path]:
    directory = repo_path(key_dir)
    return {
        "dir": directory,
        "private": directory / "private_key.pem",
        "public": directory / "public_key.pem",
        "cert": directory / "public_cert.pem",
    }


def run_openssl(*args: str) -> None:
    if not shutil.which("openssl"):
        raise RuntimeError("OpenSSL was not found on PATH.")

    command = ["openssl", *map(str, args)]
    subprocess.run(command, check=True)


def require_keys(key_dir: str) -> dict[str, Path]:
    paths = key_paths(key_dir)
    if not paths["cert"].exists():
        raise FileNotFoundError(
            f"Missing public certificate: {paths['cert']}. Run: python tools/secure_text.py init"
        )
    if not paths["private"].exists():
        raise FileNotFoundError(
            f"Missing private key: {paths['private']}. Run: python tools/secure_text.py init"
        )
    return paths


def init_keys(key_dir: str) -> None:
    paths = key_paths(key_dir)
    paths["dir"].mkdir(parents=True, exist_ok=True)

    if not paths["private"].exists():
        run_openssl("genrsa", "-out", str(paths["private"]), "3072")

    if not paths["public"].exists():
        run_openssl("rsa", "-in", str(paths["private"]), "-pubout", "-out", str(paths["public"]))

    if not paths["cert"].exists():
        config = "\n".join(
            [
                "[req]",
                "distinguished_name = dn",
                "prompt = no",
                "",
                "[dn]",
                "CN = ReadNotes Local Encryption",
                "",
            ]
        )
        with tempfile.NamedTemporaryFile("w", encoding="ascii", delete=False) as handle:
            handle.write(config)
            config_path = Path(handle.name)

        try:
            run_openssl(
                "req",
                "-new",
                "-x509",
                "-key",
                str(paths["private"]),
                "-out",
                str(paths["cert"]),
                "-days",
                "36500",
                "-config",
                str(config_path),
            )
        finally:
            config_path.unlink(missing_ok=True)

    print("Created:")
    print(f"  Private key: {paths['private']}")
    print(f"  Public key:  {paths['public']}")
    print(f"  Public cert: {paths['cert']}")
    print()
    print("Keep private_key.pem secret. Anyone with it can decrypt your encrypted text.")


def encrypt_file(key_dir: str, in_file: Path, out_file: Path) -> None:
    paths = require_keys(key_dir)
    run_openssl(
        "cms",
        "-encrypt",
        "-aes-256-gcm",
        "-binary",
        "-outform",
        "PEM",
        "-in",
        str(in_file),
        "-out",
        str(out_file),
        str(paths["cert"]),
    )


def decrypt_file(key_dir: str, in_file: Path, out_file: Path) -> None:
    paths = require_keys(key_dir)
    run_openssl(
        "cms",
        "-decrypt",
        "-inform",
        "PEM",
        "-binary",
        "-in",
        str(in_file),
        "-recip",
        str(paths["cert"]),
        "-inkey",
        str(paths["private"]),
        "-out",
        str(out_file),
    )


def encrypt_text(key_dir: str, text: str | None, out_file: Path) -> None:
    content = sys.stdin.read() if text is None else text
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", delete=False) as handle:
        handle.write(content)
        temp_input = Path(handle.name)

    try:
        encrypt_file(key_dir, temp_input, out_file)
    finally:
        temp_input.unlink(missing_ok=True)


def decrypt_text(key_dir: str, in_file: Path) -> None:
    with tempfile.NamedTemporaryFile(delete=False) as handle:
        temp_output = Path(handle.name)

    try:
        decrypt_file(key_dir, in_file, temp_output)
        sys.stdout.write(temp_output.read_text(encoding="utf-8"))
    finally:
        temp_output.unlink(missing_ok=True)


def _encrypt_string(key_dir: str, plaintext: str) -> str:
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", delete=False) as in_handle:
        in_handle.write(plaintext)
        in_path = Path(in_handle.name)
    with tempfile.NamedTemporaryFile(delete=False) as out_handle:
        out_path = Path(out_handle.name)
    try:
        encrypt_file(key_dir, in_path, out_path)
        return out_path.read_text(encoding="ascii")
    finally:
        in_path.unlink(missing_ok=True)
        out_path.unlink(missing_ok=True)


def _decrypt_string(key_dir: str, ciphertext: str) -> str:
    with tempfile.NamedTemporaryFile("w", encoding="ascii", delete=False) as in_handle:
        in_handle.write(ciphertext)
        in_path = Path(in_handle.name)
    with tempfile.NamedTemporaryFile(delete=False) as out_handle:
        out_path = Path(out_handle.name)
    try:
        decrypt_file(key_dir, in_path, out_path)
        return out_path.read_text(encoding="utf-8")
    finally:
        in_path.unlink(missing_ok=True)
        out_path.unlink(missing_ok=True)


def _iter_markdown(root: Path):
    if root.is_file():
        yield root
        return
    yield from root.rglob("*.md")


def _process_blocks(key_dir: str, root: Path, mode: str) -> tuple[int, int]:
    files_changed = 0
    blocks_changed = 0
    for path in _iter_markdown(root):
        original = path.read_text(encoding="utf-8")
        file_blocks = 0

        def replace(match: re.Match) -> str:
            nonlocal file_blocks
            header, body, footer = match.group(1), match.group(2), match.group(3)
            is_encrypted = CMS_MARKER in body
            if mode == "encrypt" and not is_encrypted:
                file_blocks += 1
                return f"{header}{_encrypt_string(key_dir, body.strip())}{footer}"
            if mode == "decrypt" and is_encrypted:
                file_blocks += 1
                return f"{header}{_decrypt_string(key_dir, body.strip())}{footer}"
            return match.group(0)

        updated = NOTE_BLOCK_RE.sub(replace, original)
        if updated != original:
            path.write_text(updated, encoding="utf-8")
            files_changed += 1
            blocks_changed += file_blocks
            print(f"{mode}: {path} ({file_blocks} block(s))")
    return files_changed, blocks_changed


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Encrypt text or files with local RSA keys using OpenSSL CMS."
    )
    parser.add_argument(
        "action",
        choices=["init", "encrypt-text", "decrypt-text", "encrypt-file", "decrypt-file",
                 "encrypt-notes", "decrypt-notes"],
    )
    parser.add_argument("--text", help="Text to encrypt. If omitted, stdin is used.")
    parser.add_argument("--in-file", help="Input file path.")
    parser.add_argument("--out-file", help="Output file path.")
    parser.add_argument("--key-dir", default="keys", help="Directory for key files.")
    parser.add_argument(
        "--notes-dir",
        default="ReadNotes",
        help="Root directory (or single .md file) to scan for /** Encrypt ... **/ blocks.",
    )
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    try:
        if args.action == "init":
            init_keys(args.key_dir)
        elif args.action == "encrypt-text":
            if not args.out_file:
                parser.error("encrypt-text requires --out-file")
            encrypt_text(args.key_dir, args.text, repo_path(args.out_file))
        elif args.action == "decrypt-text":
            if not args.in_file:
                parser.error("decrypt-text requires --in-file")
            decrypt_text(args.key_dir, repo_path(args.in_file))
        elif args.action == "encrypt-file":
            if not args.in_file or not args.out_file:
                parser.error("encrypt-file requires --in-file and --out-file")
            encrypt_file(args.key_dir, repo_path(args.in_file), repo_path(args.out_file))
        elif args.action == "decrypt-file":
            if not args.in_file or not args.out_file:
                parser.error("decrypt-file requires --in-file and --out-file")
            decrypt_file(args.key_dir, repo_path(args.in_file), repo_path(args.out_file))
        elif args.action == "encrypt-notes":
            notes_root = repo_path(args.notes_dir)
            files_changed, blocks_changed = _process_blocks(args.key_dir, notes_root, "encrypt")
            print(f"\nEncrypted {blocks_changed} block(s) in {files_changed} file(s).")
        elif args.action == "decrypt-notes":
            notes_root = repo_path(args.notes_dir)
            files_changed, blocks_changed = _process_blocks(args.key_dir, notes_root, "decrypt")
            print(f"\nDecrypted {blocks_changed} block(s) in {files_changed} file(s).")
    except (FileNotFoundError, RuntimeError, subprocess.CalledProcessError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
