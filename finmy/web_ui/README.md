# Pipeline web interface

Launch the original pipeline interface from the checkout with
`streamlit run finmy/web_interface.py`. Its public class is available as
`from finmy.web_interface import FinMyceliumWebInterface`. The launcher loads
local environment settings when started.

The dataset workbench has its own entry point, `python -m finmy.workbench`, for
catalog selection, saved search and build tasks, and review.
[Workbench guide](../../docs/workflows/event-workbench.md)

| Directory or module | Responsibility |
| --- | --- |
| `main.py`, `state.py`, `styles.py` | Application routing, Streamlit session state and shared styles |
| `components/` | Navigation, configuration uploads and input forms |
| `pages/` | Pipeline, results and other screens |
| `services/` | Data collection and reconstruction |
| `utils/` | Input validation, display formatting and history loading |

The implementation class and application runner live in [main.py](main.py).
