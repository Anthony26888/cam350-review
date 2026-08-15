import argparse
import os
import shutil
import subprocess
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from license.registry import LicenseRegistry, days_left_of, status_of
from license.verify import build_license_key, verify_license_key

_RED = "\033[91m"
_YELLOW = "\033[93m"
_GREEN = "\033[92m"
_CYAN = "\033[96m"
_BOLD = "\033[1m"
_RESET = "\033[0m"


def _color(text: str, code: str) -> str:
    if os.environ.get("NO_COLOR") or not sys.stdout.isatty():
        return text
    return f"{code}{text}{_RESET}"


def _red(t): return _color(t, _RED)
def _yellow(t): return _color(t, _YELLOW)
def _green(t): return _color(t, _GREEN)
def _cyan(t): return _color(t, _CYAN)
def _bold(t): return _color(t, _BOLD)


def _default_key_path() -> Path:
    env = os.environ.get("CAM350_LICENSE_PRIVATE_KEY")
    if env:
        return Path(env)
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent / "private_key.pem"
    here = Path(__file__).resolve().parent.parent
    return here / "secrets" / "private_key.pem"


def _load_private_key(key_path: Path) -> str:
    if not key_path.exists():
        _fail(
            f"private key not found at {key_path}. "
            "Copy private_key.pem next to this tool (only needed for create/renew)."
        )
    return key_path.read_text(encoding="utf-8")


def _load_registry(path: str | None = None) -> LicenseRegistry:
    if path:
        return LicenseRegistry(Path(path))
    return LicenseRegistry()


def _copy_to_clipboard(text: str) -> bool:
    try:
        import pyperclip  # type: ignore

        pyperclip.copy(text)
        return True
    except Exception:
        pass
    for tool in (["pbcopy"], ["xclip", "-selection", "clipboard"], ["clip"]):
        if shutil.which(tool[0]):
            try:
                subprocess.run(
                    tool, input=text.encode("utf-8"), check=True, timeout=10
                )
                return True
            except Exception:
                pass
    return False


def _parse_expiry(value: str) -> str:
    try:
        datetime.strptime(value, "%Y-%m-%d")
    except ValueError:
        _fail("expiry must be in YYYY-MM-DD format.")
    return value


def _fail(message: str) -> None:
    print(f"ERROR: {message}", file=sys.stderr)
    sys.exit(1)


def _pause() -> None:
    if sys.stdin is not None and sys.stdin.isatty():
        try:
            input("\nPress Enter to continue...")
        except EOFError:
            pass


def _expiry_from_days(days: int) -> str:
    return (date.today() + timedelta(days=days)).isoformat()


def _status_label(status: str) -> str:
    if status == "expired":
        return _red("EXPIRED")
    if status == "expiring":
        return _yellow("EXPIRING")
    if status == "valid":
        return _green("VALID")
    return _red("INVALID")


def _print_licenses(licenses, registry: LicenseRegistry) -> None:
    if not licenses:
        print(_yellow("No licenses found."))
        return
    header = f"{_bold('No.')}  {'Customer':<22} {'Device':<14} {'HWID':<34} {'Expiry':<12} {'Left':<6} {'Status':<10}"
    print(header)
    print("-" * len(header))
    today = date.today().isoformat()
    for i, lic in enumerate(licenses, start=1):
        days = days_left_of(lic.get("expiry", ""), today)
        status = status_of(lic.get("expiry", ""), today, registry.warning_days)
        left = _red(str(days)) if status == "expired" else _yellow(str(days)) if status == "expiring" else _green(str(days))
        print(
            f"{i:<4} {str(lic.get('customer', ''))[:22]:<22} "
            f"{str(lic.get('device', ''))[:14]:<14} "
            f"{str(lic.get('hwid', ''))[:34]:<34} "
            f"{lic.get('expiry', ''):<12} {left:<6} {_status_label(status):<10}"
        )


def _get_record(registry: LicenseRegistry, records=None, prompt: str = "Choose number: ") -> dict:
    records = records if records is not None else registry.all()
    if not records:
        _fail("No licenses in registry yet.")
    _print_licenses(records, registry)
    try:
        choice = int(input(prompt).strip())
        if choice < 1 or choice > len(records):
            raise ValueError
    except (ValueError, EOFError):
        _fail("Invalid choice.")
    return records[choice - 1]


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------

def _cmd_create(registry, args) -> None:
    hwid = args.hwid or input("Machine HWID: ").strip()
    customer = args.customer or input("Customer name: ").strip()
    device = args.device or input("Device name (optional): ").strip()
    notes = args.note or ""
    if args.days is not None:
        expiry = _expiry_from_days(args.days)
    else:
        raw = input("Duration in days (blank for custom date): ").strip()
        if raw.isdigit():
            expiry = _expiry_from_days(int(raw))
        else:
            expiry = args.expiry or input("Expiry (YYYY-MM-DD): ").strip()
    expiry = _parse_expiry(expiry)
    if not hwid or not customer:
        _fail("hwid and customer are required.")

    private_key = _load_private_key(Path(args.key))
    issued_at = datetime.now().isoformat(timespec="seconds")
    key = build_license_key(private_key, hwid, customer, expiry, issued_at)
    print(_green("\nLicense key created:"))
    print(key)
    print()

    record = registry.add(
        hwid=hwid, customer=customer, expiry=expiry, issued_at=issued_at,
        device=device, notes=notes, key=key,
    )
    print(_green(f"Saved to registry: {registry.path}"))
    if _copy_to_clipboard(key):
        print("Key copied to clipboard. Send to customer (Ctrl+V).")
    else:
        print("Copy the key above and send to customer.")
    if args.customer is None:
        print(f"\n{customer} | {device} | expiry {expiry}")


def _cmd_verify(registry, args) -> None:
    key = args.key or args.key_arg
    if not key:
        key = input("License key: ").strip()
    hwid = args.hwid or input("Machine HWID: ").strip()
    ok, reason, payload = verify_license_key(key, hwid)
    if ok and payload:
        days = days_left_of(payload.get("expiry", ""))
        print(
            _green(f"OK  valid until {payload['expiry']} "
                   f"({days} days left) | customer: {payload['customer']}")
        )
    else:
        print(f"FAIL  reason: {reason}")


def _cmd_list(registry, args=None) -> None:
    _print_licenses(registry.all(), registry)


def _cmd_check(registry, args) -> None:
    records = registry.all()
    if args.customer:
        records = [r for r in records if args.customer.lower() in r.get("customer", "").lower()]
    if args.hwid:
        records = [r for r in records if r.get("hwid") == args.hwid]
    if not records:
        print(_yellow("No matching license found."))
        return
    _print_licenses(records, registry)
    for r in records:
        renewals = r.get("renewals") or []
        if renewals:
            print(f"\n  {r.get('customer')} renewals: {len(renewals)}")


def _cmd_due(registry, args) -> None:
    days = args.days if args.days is not None else registry.warning_days
    today = date.today().isoformat()
    due = [
        r for r in registry.all()
        if status_of(r.get("expiry", ""), today, days) in ("expired", "expiring")
    ]
    if not due:
        print(_green(f"No licenses expiring within {days} days or already expired."))
        return
    print(_yellow(f"Licenses due within {days} days or already expired:"))
    _print_licenses(due, registry)


def _cmd_renew(registry, args) -> None:
    records = registry.all()
    if args.hwid:
        target = registry.find_by_hwid(args.hwid)
        records = [target] if target else []
    else:
        today = date.today().isoformat()
        due = [r for r in records if status_of(r.get("expiry", ""), today, registry.warning_days) in ("expired", "expiring")]
        records = due or records
    if not records:
        print(_yellow("No licenses to renew."))
        return

    target = None
    if len(records) == 1:
        target = records[0]
        print(f"Renewing: {target.get('customer')} | {target.get('device')} | expiry {target.get('expiry')}")
    else:
        print(_yellow("Choose which license to renew:"))
        target = _get_record(registry, records)

    days = args.days or int(input("Days to add: ").strip())
    if days <= 0:
        _fail("days must be positive.")

    private_key = _load_private_key(Path(args.key))
    hwid = target["hwid"]
    customer = target["customer"]
    when = datetime.now().isoformat(timespec="seconds")
    old_expiry = target.get("expiry", "")
    base = max(old_expiry, date.today().isoformat()) if old_expiry else date.today().isoformat()
    new_expiry = (date.fromisoformat(base) + timedelta(days=days)).isoformat()
    new_key = build_license_key(private_key, hwid, customer, new_expiry, when)
    record = registry.renew(target["id"], days, new_key, when=when)
    if record is None:
        _fail("Could not renew license.")
    print(_green(f"\nRenewed until {record['expiry']} (+{days} days)."))
    print("New license key:")
    print(record["key"])
    print()
    if _copy_to_clipboard(record["key"]):
        print("New key copied to clipboard. Send to customer (Ctrl+V).")


def _cmd_history(registry, args) -> None:
    records = registry.all()
    if args.customer:
        records = [r for r in records if args.customer.lower() in r.get("customer", "").lower()]
    if not records:
        print(_yellow("No records found."))
        return
    for r in records:
        renewals = r.get("renewals") or []
        print(f"\n{_bold(r.get('customer'))} | {r.get('device')} | HWID {r.get('hwid')} | current expiry {r.get('expiry')}")
        if not renewals:
            print("  (no renewals yet)")
            continue
        for i, h in enumerate(renewals, start=1):
            print(f"  #{i} {h.get('date')}  +{h.get('days')}d  "
                  f"{h.get('old_expiry')} -> {h.get('new_expiry')}")


def _cmd_stats(registry, args=None) -> None:
    today = date.today().isoformat()
    all_ = registry.all()
    expired = sum(1 for r in all_ if status_of(r.get("expiry", ""), today, registry.warning_days) == "expired")
    expiring = sum(1 for r in all_ if status_of(r.get("expiry", ""), today, registry.warning_days) == "expiring")
    valid = len(all_) - expired - expiring
    print(f"Total licenses : {len(all_)}")
    print(f"  {_green('Valid')}     : {valid}")
    print(f"  {_yellow('Expiring')}  : {expiring} (within {registry.warning_days} days)")
    print(f"  {_red('Expired')}   : {expired}")


# ---------------------------------------------------------------------------
# Interactive menu
# ---------------------------------------------------------------------------

def _menu_loop() -> None:
    registry = _load_registry()
    while True:
        print("\n" + _bold("=== CAM350 Review License Tool ==="))
        print(" 1. Cấp license mới")
        print(" 2. Kiểm tra license key")
        print(" 3. Danh sách license đã cấp")
        print(" 4. Kiểm tra khách hàng")
        print(" 5. Kiểm tra theo máy (HWID)")
        print(" 6. Sắp hết hạn / đã hết hạn")
        print(" 7. Gia hạn license")
        print(" 8. Lịch sử gia hạn")
        print(" 9. Thống kê tổng quan")
        print(" 10. Thoát")
        try:
            choice = input("Chọn (1-10): ").strip()
        except EOFError:
            break
        if choice == "10":
            break
        try:
            if choice == "1":
                _cmd_create(registry, _Args())
            elif choice == "2":
                _cmd_verify(registry, _Args())
            elif choice == "3":
                _cmd_list(registry)
            elif choice == "4":
                _cmd_check(registry, _Args(customer=_ask_customer(registry)))
            elif choice == "5":
                _cmd_check(registry, _Args(hwid=input("HWID: ").strip()))
            elif choice == "6":
                _cmd_due(registry, _Args())
            elif choice == "7":
                _cmd_renew(registry, _Args())
            elif choice == "8":
                _cmd_history(registry, _Args())
            elif choice == "9":
                _cmd_stats(registry)
            else:
                print(_yellow("Invalid choice."))
        except SystemExit:
            pass
        _pause()


def _ask_customer(registry: LicenseRegistry) -> str:
    customers = sorted({r.get("customer", "") for r in registry.all() if r.get("customer")})
    if customers:
        print("Customers:")
        for i, name in enumerate(customers, start=1):
            print(f"  {i}. {name}")
        try:
            choice = input("Choose number (or enter name): ").strip()
            if choice.isdigit():
                idx = int(choice)
                if 1 <= idx <= len(customers):
                    return customers[idx - 1]
                raise ValueError
            return choice
        except (ValueError, EOFError):
            pass
    return input("Customer name: ").strip()


class _Args:
    def __init__(self, **kwargs) -> None:
        self.hwid = kwargs.get("hwid")
        self.customer = kwargs.get("customer")
        self.device = kwargs.get("device")
        self.note = kwargs.get("note")
        self.days = kwargs.get("days")
        self.expiry = kwargs.get("expiry")
        self.key = kwargs.get("key") or str(_default_key_path())
        self.warning_days = kwargs.get("warning_days")


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="license_tool",
        description="CAM350 Review license seller tool (create, verify, monitor, renew).",
    )
    parser.add_argument(
        "--key",
        default=str(_default_key_path()),
        help="Path to private_key.pem (default: next to this tool / secrets)",
    )
    parser.add_argument(
        "--registry",
        default=None,
        help="Path to licenses.json (default: next to this tool / secrets)",
    )
    sub = parser.add_subparsers(dest="command")

    create = sub.add_parser("create", help="Create a new license key")
    create.add_argument("--hwid", help="Machine HWID of the customer")
    create.add_argument("--customer", help="Customer name")
    create.add_argument("--device", help="Device name (optional)")
    create.add_argument("--note", help="Notes (optional)")
    create.add_argument("--expiry", help="Expiry date YYYY-MM-DD")
    create.add_argument("--days", type=int, help="Length in days (overrides --expiry)")
    create.set_defaults(func=_cmd_create)

    verify = sub.add_parser("verify", help="Verify a license key against a HWID")
    verify.add_argument("--hwid", help="Machine HWID")
    verify.add_argument("--license-key", dest="key_arg", help="License key string")
    verify.set_defaults(func=_cmd_verify)

    sub.add_parser("list", help="List all issued licenses").set_defaults(func=_cmd_list)

    check = sub.add_parser("check", help="Check a customer or machine")
    check.add_argument("--customer", help="Customer name (substring)")
    check.add_argument("--hwid", help="Machine HWID")
    check.set_defaults(func=_cmd_check)

    due = sub.add_parser("due", help="Show licenses expiring soon / expired")
    due.add_argument("--days", type=int, help="Warning window in days (default: registry setting)")
    due.set_defaults(func=_cmd_due)

    renew = sub.add_parser("renew", help="Renew a license")
    renew.add_argument("--hwid", help="Machine HWID (if omitted, pick from list)")
    renew.add_argument("--days", type=int, help="Days to add")
    renew.set_defaults(func=_cmd_renew)

    history = sub.add_parser("history", help="Show renewal history")
    history.add_argument("--customer", help="Customer name (substring)")
    history.set_defaults(func=_cmd_history)

    sub.add_parser("stats", help="Overview statistics").set_defaults(func=_cmd_stats)

    parser.set_defaults(func=None)
    return parser


def main() -> None:
    args = sys.argv[1:]
    if not args:
        _menu_loop()
        return
    parser = _build_parser()
    namespace = parser.parse_args(args)
    if namespace.command is None:
        parser.print_help()
        return
    registry = _load_registry(namespace.registry)
    if namespace.command == "verify":
        _cmd_verify(registry, namespace)
        return
    namespace.func(registry, namespace)


if __name__ == "__main__":
    sys.exit(main())