"""Compatibility entry point for the original FinMycelium Streamlit interface."""
from dotenv import load_dotenv
from finmy.web_ui.main import FinMyceliumWebInterface, main as refactored_main

__all__ = ["FinMyceliumWebInterface", "main", "refactored_main"]


def main():
    load_dotenv()
    refactored_main()


if __name__ == "__main__":
    main()
