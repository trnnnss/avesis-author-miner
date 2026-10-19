"""Profil keşfi için geriye uyumlu giriş noktası."""

import sys

from avesis_miner.cli import main

if __name__ == "__main__":
    raise SystemExit(main(["discover", *sys.argv[1:]]))
