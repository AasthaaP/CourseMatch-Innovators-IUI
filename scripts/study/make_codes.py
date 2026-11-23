"""Write data/study/codes.csv with participant codes P001..P0NN (final spec 10.6). The file is git-ignored.

Run: python scripts/study/make_codes.py --n 30
"""
import argparse
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "data/study/codes.csv"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=30)
    args = ap.parse_args()
    if not 1 <= args.n <= 999:
        raise SystemExit("--n must be 1 to 999")
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text("code\n" + "".join(f"P{i:03d}\n" for i in range(1, args.n + 1)))
    print(f"wrote {args.n} codes to {OUT.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
