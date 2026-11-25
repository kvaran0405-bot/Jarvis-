"""One-time set-up: a permanent signing key for the phone app, so every new version installs over the old one
(and the app can update itself). Run on the laptop:  python -m jarvis signing-key

The key is made on the laptop, a backup is kept in ~/JARVIS/Signing (never in the repository), and the two values
GitHub needs are put on the clipboard one at a time while the GitHub "new secret" page opens."""
from __future__ import annotations

import base64
import datetime
import secrets
import subprocess
import sys
import webbrowser
from pathlib import Path

REPO = "kvaran0405-bot/Jarvis-"
NEW_SECRET = f"https://github.com/{REPO}/settings/secrets/actions/new"
HOME = Path.home() / "JARVIS" / "Signing"


def make_keystore(password: str) -> bytes:
    """A PKCS12 keystore with one RSA key, alias "jarvis" (what the Android build expects)."""
    try:
        from cryptography import x509
        from cryptography.hazmat.primitives import hashes, serialization
        from cryptography.hazmat.primitives.asymmetric import rsa
        from cryptography.hazmat.primitives.serialization import pkcs12
        from cryptography.x509.oid import NameOID
    except ImportError:
        subprocess.run([sys.executable, "-m", "pip", "install", "-q", "cryptography"], check=True)
        return make_keystore(password)
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "JARVIS"), x509.NameAttribute(NameOID.ORGANIZATION_NAME, "Personal")])
    now = datetime.datetime.now(datetime.timezone.utc)
    cert = (x509.CertificateBuilder().subject_name(name).issuer_name(name).public_key(key.public_key())
            .serial_number(x509.random_serial_number()).not_valid_before(now - datetime.timedelta(days=1))
            .not_valid_after(now + datetime.timedelta(days=365 * 30)).sign(key, hashes.SHA256()))
    return pkcs12.serialize_key_and_certificates(b"jarvis", key, cert, None,
                                                 serialization.BestAvailableEncryption(password.encode()))


def _clip(text: str) -> bool:
    try:
        if sys.platform == "win32":
            subprocess.run(["clip"], input=text.encode("utf-16-le"), check=True)
        elif sys.platform == "darwin":
            subprocess.run(["pbcopy"], input=text.encode(), check=True)
        else:
            subprocess.run(["xclip", "-selection", "clipboard"], input=text.encode(), check=True)
        return True
    except Exception:  # noqa: BLE001
        return False


def setup() -> int:
    HOME.mkdir(parents=True, exist_ok=True)
    store, pw_file = HOME / "jarvis-app.p12", HOME / "password.txt"
    if store.exists() and pw_file.exists():
        password = pw_file.read_text().strip()
        print("Using your existing JARVIS app key (", store, ")")
    else:
        password = secrets.token_hex(16)
        store.write_bytes(make_keystore(password))
        pw_file.write_text(password)
        print("Made a permanent signing key for the JARVIS app. Backup:", HOME)
    b64 = base64.b64encode(store.read_bytes()).decode()
    steps = [("JARVIS_KEYSTORE_B64", b64), ("JARVIS_KEYSTORE_PASSWORD", password)]
    print("\nFirst make sure you're signed in to GitHub in your browser (as the account that owns JARVIS):\n"
          "a 'Page not found' / 404 page means you're signed out. Sign in, then reload the page.")
    print("\nGitHub needs two secrets. For each one: the page opens, the value is already copied,\n"
          "type the name, paste the value (Ctrl+V), click 'Add secret'.\n")
    for i, (name, value) in enumerate(steps, 1):
        copied = _clip(value)
        webbrowser.open(NEW_SECRET)
        print(f"{i}/2  Name: {name}")
        print("     Value: " + ("copied, just paste it" if copied else f"(copy this) {value}"))
        input("     Press Enter here when it's added... ")
    _clip("")
    print("\nDone. Tell JARVIS (or Claude) and the next phone app is built with this key.\n"
          "Install that one last time by hand (uninstall the old app first); after that it updates itself.")
    return 0
