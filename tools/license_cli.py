import argparse
import os
import subprocess
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from license.verify import build_license_key, verify_license_key


def _default_key_path() -> Path:
    env = os.environ.get("CAM350_LICENSE_PRIVATE_KEY")
    if env:
        return Path(env)
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent / "private_key.pem"
    here = Path(__file__).resolve().parent.parent
    return here / "secrets" / "private_key.pem"


def _is_interactive() -> bool:
    return sys.stdin is not None and sys.stdin.isatty()


def _pause() -> None:
    if _is_interactive():
        try:
            input("\nPress Enter to exit...")
        except EOFError:
            pass


def _fail(message: str) -> None:
    print(f"ERROR: {message}", file=sys.stderr)
    _pause()
    sys.exit(1)


def _load_private_key(key_path: Path) -> str:
    if not key_path.exists():
        _fail(
            f"private key not found at {key_path}. "
            f"Copy private_key.pem next to license_cli.exe (or run `python tools/keygen.py` first)."
        )
    return key_path.read_text(encoding="utf-8")


def _parse_expiry(value: str) -> str:
    try:
        datetime.strptime(value, "%Y-%m-%d")
    except ValueError:
        _fail("--expiry must be in YYYY-MM-DD format.")
    return value


def _copy_to_clipboard(text: str) -> bool:
    try:
        subprocess.run(
            ["clip"], input=text.encode("ascii"), check=True, timeout=10
        )
        return True
    except Exception:
        return False


def _cmd_create(args) -> None:
    hwid = args.hwid or input("Machine HWID: ").strip()
    customer = args.customer or input("Customer name: ").strip()
    if args.days is not None:
        expiry = (date.today() + timedelta(days=args.days)).isoformat()
    else:
        expiry = args.expiry or input("Expiry (YYYY-MM-DD): ").strip()
    expiry = _parse_expiry(expiry)

    if not hwid or not customer:
        _fail("hwid and customer are required.")

    private_key = _load_private_key(Path(args.key))
    issued_at = datetime.now().isoformat(timespec="seconds")
    key = build_license_key(private_key, hwid, customer, expiry, issued_at)
    print(key)
    print()
    if _copy_to_clipboard(key):
        print("Key copied to clipboard. Press Ctrl+V to paste.")
    else:
        print("Select the key above and copy it manually (Ctrl+C).")
    _pause()


def _cmd_verify(args) -> None:
    key = args.key
    if not key:
        key = input("License key: ").strip()
    hwid = args.hwid or input("Machine HWID: ").strip()
    ok, reason, payload = verify_license_key(key, hwid)
    if ok:
        print(f"OK  valid until {payload['expiry']} (customer: {payload['customer']})")
    else:
        print(f"FAIL  reason: {reason}")
    _pause()
    sys.exit(0 if ok else 1)


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="license_cli",
        description="CAM350 Review license seller tool (creates license keys).",
    )
    parser.add_argument(
        "--key",
        default=str(_default_key_path()),
        help="Path to private_key.pem (default: next to this exe)",
    )
    sub = parser.add_subparsers(dest="command")

    create = sub.add_parser("create", help="Create a new license key")
    create.add_argument("--hwid", help="Machine HWID of the customer")
    create.add_argument("--customer", help="Customer name")
    create.add_argument("--expiry", help="Expiry date YYYY-MM-DD")
    create.add_argument("--days", type=int, help="Subscription length in days (overrides --expiry)")
    create.set_defaults(func=_cmd_create)

    verify = sub.add_parser("verify", help="Verify a license key against a HWID")
    verify.add_argument("--hwid", help="Machine HWID")
    verify.add_argument("--license-key", dest="key", help="License key string")
    verify.set_defaults(func=_cmd_verify)

    args = parser.parse_args()
    if args.command is None:
        args.command = "create"
        args.func = _cmd_create
        args.hwid = None
        args.customer = None
        args.expiry = None
        args.days = None
    args.func(args)


if __name__ == "__main__":
    sys.exit(main())
