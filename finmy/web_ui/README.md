# FinMycelium Web UI - Refactored Architecture

This directory contains the refactored web interface for FinMycelium, organized into a modular architecture for better maintainability and extensibility.

## Directory Structure

```
web_ui/
├── __init__.py              # Module exports
├── main.py                  # Main entry point and routing
├── state.py                 # Session state management
├── styles.py                # CSS styles
├── components/              # Reusable UI components
│   ├── __init__.py
│   ├── sidebar.py          # Navigation sidebar
│   ├── config_uploader.py   # Configuration file uploader
│   └── input_forms.py      # Input form components
├── pages/                   # Page renderers
│   ├── __init__.py
│   ├── home_page.py        # Home page
│   ├── pipeline_page.py    # Pipeline/analysis page
│   ├── results_page.py     # Results page router
│   ├── about_page.py       # About page
│   └── results/            # Result page renderers
│       ├── __init__.py
│       ├── agent_results.py    # Agent-based results
│       └── class_results.py    # Class-based results
├── services/                # Business logic services
│   ├── __init__.py
│   ├── data_collector_service.py    # Data collection logic
│   └── reconstruction_service.py    # Event reconstruction logic
└── utils/                   # Utility functions
    ├── __init__.py
    ├── validators.py        # Validation utilities
    └── formatters.py        # Formatting utilities
```

## Architecture Overview

### Separation of Concerns

1. **State Management** (`state.py`)
   - Centralized session state management
   - Provides clean API for state operations

2. **Components** (`components/`)
   - Reusable UI components
   - Self-contained and testable

3. **Pages** (`pages/`)
   - Page-level renderers
   - Coordinate components and services

4. **Services** (`services/`)
   - Business logic separated from UI
   - Data processing and pipeline execution

5. **Utils** (`utils/`)
   - Shared utility functions
   - Validation and formatting helpers

6. **Styles** (`styles.py`)
   - Centralized CSS styling
   - Consistent UI appearance

## Key Improvements

1. **Modularity**: Code is organized into logical modules
2. **Maintainability**: Easier to locate and modify specific functionality
3. **Testability**: Services and components can be tested independently
4. **Reusability**: Components can be reused across pages
5. **Scalability**: Easy to add new pages, components, or services

## Usage

The refactored interface maintains backward compatibility. Existing code using:

```python
from finmy.web_interface import FinMyceliumWebInterface
```

will continue to work, as `web_interface.py` now imports from the refactored module.

## Migration Notes

- All original functionality is preserved
- The original `web_interface.py` file now acts as a compatibility layer
- New features should be added to the refactored modules
- The original file can be removed once all dependencies are updated

## Future Enhancements

- Add unit tests for services and components
- Implement error handling middleware
- Add logging infrastructure
- Create component library documentation
- Add type hints throughout

