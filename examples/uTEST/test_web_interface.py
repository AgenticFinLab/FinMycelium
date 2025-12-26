"""
Web interface for FinMycelium - Financial Event Reconstruction System
Provides a user-friendly interface for reconstructing financial events
through multiple data sources and AI-powered analysis.

NOTE: This file has been refactored. The new implementation is in finmy/web_ui/.
This file now imports from the refactored module for backward compatibility.
"""

from dotenv import load_dotenv

from finmy.web_ui.main import main as refactored_main

load_dotenv()

if __name__ == "__main__":
    refactored_main()
