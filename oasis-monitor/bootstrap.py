"""Decode pinned, locally tested scanner sources on first runner execution only."""
from pathlib import Path
import base64
import gzip
import hashlib

ROOT = Path(__file__).resolve().parent
EXPECTED = {
    "scanner.py": "9dd8760259bd23355cc0b96db2a20b45ce35718f727540cc99d5f3292708242f",
    "test_scanner.py": "66a02674fa2ebfe5f090df984e643a2ccdc66460f760aa95c474b00dfa3c8a91",
}
for name, digest in EXPECTED.items():
    dest = ROOT / name
    if dest.exists():
        print(f"Existing readable source: {name}")
        continue
    source = ROOT / f"{name}.gz.b64"
    raw = gzip.decompress(base64.b64decode(source.read_text().strip(), validate=True))
    actual = hashlib.sha256(raw).hexdigest()
    if actual != digest:
        raise SystemExit(f"Bootstrap SHA-256 mismatch for {name}: {actual}")
    dest.write_bytes(raw)
    print(f"Decoded verified source {name}, SHA-256 {actual}")
