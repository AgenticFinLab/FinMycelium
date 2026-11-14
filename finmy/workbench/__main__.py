"""Loopback-only launcher; no model or search service is started."""

import argparse
from pathlib import Path
import sys


def main():
    parser = argparse.ArgumentParser(description="Local FinMycelium event workbench")
    parser.add_argument("--port", type=int, default=8537)
    parser.add_argument("--dataset-root", help="Local EPG-dataset checkout owning the workbench workspace")
    args = parser.parse_args()
    if not 1 <= args.port <= 65535:
        parser.error("port must be in 1..65535")
    if args.dataset_root:
        from finmy.workbench.workspace import resolve_workspace, select_workspace
        project = Path(__file__).resolve().parents[2]
        try:
            select_workspace(project, args.dataset_root, current=resolve_workspace(project))
        except (ValueError, OSError) as exc:
            parser.error(str(exc))
    from streamlit.web import cli
    from finmy.workbench.ui import theme_args
    sys.argv = ["streamlit", "run", str(Path(__file__).with_name("app.py")),
                "--server.address", "127.0.0.1", "--server.port", str(args.port),
                "--server.headless", "true", "--browser.gatherUsageStats", "false",
                "--server.maxUploadSize", "20",
                *theme_args()]
    cli.main()


if __name__ == "__main__":
    main()
