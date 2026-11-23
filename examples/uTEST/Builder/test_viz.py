"""Render a saved ordinary event as a PNG, or use --interactive to open it."""
import argparse
import json
import os
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("graph", type=Path, nargs="?", default=Path(
        "docs/assets/builder_results/ftx_crypto_exchange_collapse/FinalEventCascade.json"))
    parser.add_argument("-o", "--output", type=Path, default=Path("output/event-timeline.png"))
    parser.add_argument("--interactive", action="store_true", default=os.getenv("INTERACTIVE_VIZ") == "1")
    args = parser.parse_args()
    import matplotlib.pyplot as plt
    if not args.interactive:
        plt.switch_backend("Agg")
        args.output.parent.mkdir(parents=True, exist_ok=True)
    from finmy.builder.agent_build.visualizer import EventCascadeVisualizer
    graph = json.loads(args.graph.read_text(encoding="utf-8"))
    EventCascadeVisualizer().plot_cascade(graph, None if args.interactive else str(args.output))
    if args.interactive:
        plt.show()
    else:
        print(args.output)


if __name__ == "__main__":
    main()
