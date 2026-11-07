"""Loopback-only launcher; no model or search service is started."""

import argparse
from pathlib import Path
import sys


def main():
    parser = argparse.ArgumentParser(description="Local FinMycelium event workbench")
    parser.add_argument("--port", type=int, default=8537)
    args = parser.parse_args()
    if not 1 <= args.port <= 65535:
        parser.error("port must be in 1..65535")
    from streamlit.web import cli
    sys.argv = ["streamlit", "run", str(Path(__file__).with_name("app.py")),
                "--server.address", "127.0.0.1", "--server.port", str(args.port),
                "--server.headless", "true", "--browser.gatherUsageStats", "false",
                "--server.maxUploadSize", "20",
                "--theme.base", "light", "--theme.primaryColor", "#187968"]
    cli.main()


if __name__ == "__main__":
    main()
