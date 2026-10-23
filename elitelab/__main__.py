"""`python -m elitelab` entry point."""
import argparse

from . import config, server


def main():
    ap = argparse.ArgumentParser(prog="elitelab", description="Self-hosted live dashboard for Elite Dangerous")
    ap.add_argument("--host", default=config.HOST, help="bind address (default %(default)s)")
    ap.add_argument("--port", type=int, default=config.PORT, help="port (default %(default)s)")
    ap.add_argument("--journals", default=None, help="journal directory (default: Saved Games or /journals)")
    args = ap.parse_args()
    if args.journals:
        config.JOURNAL_DIR = args.journals
    server.serve(args.host, args.port)


if __name__ == "__main__":
    main()
