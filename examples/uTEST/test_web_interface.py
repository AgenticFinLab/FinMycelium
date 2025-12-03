"""
xxxxxxxxxxxxxxx


Run:
streamlit run examples/utest/test_web_interface.py

"""

import streamlit as st

from finmy.web_interface import FinMyceliumWebInterface


if __name__ == "__main__":
    try:
        app = FinMyceliumWebInterface()
        app.run()
    except Exception as e:
        st.error(f"Application error: {e}")
        st.info("Please refresh the page and try again.")
