import argparse
import os
import sys
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ed25519


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate an Ed25519 keypair for the CAM350 Review license system."
    )
    parser.add_argument(
        "--out",
        default="secrets",
        help="Output directory for private_key.pem and public_key.pem (default: secrets)",
    )
    args = parser.parse_args()

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    private_key = ed25519.Ed25519PrivateKey.generate()
    public_key = private_key.public_key()

    private_pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )
    public_pem = public_key.public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    )

    private_path = out_dir / "private_key.pem"
    public_path = out_dir / "public_key.pem"
    private_path.write_bytes(private_pem)
    public_path.write_bytes(public_pem)

    print(f"Private key saved:  {private_path}")
    print(f"Public key saved:   {public_path}")
    print()
    print("PUBLIC KEY (embed this in license/verify.py):")
    print(public_pem.decode("utf-8"))
    print("KEEP private_key.pem SECRET and BACK IT UP. Never ship it.")


if __name__ == "__main__":
    sys.exit(main())
