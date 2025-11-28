"""
Implementation of a Financial Event Pipeline Based on Rules, Foundational Principles, and Established Concepts

This method reconstructs financial events by first providing the LMs with a set of manually crafted or predefined rules that reflect core financial principles and well-established concepts. These rules are included directly in the prompt to guide the model during reconstruction, and the entire process is completed in a single inference pass.

prompt (rules + guidance) -> LM -> EventCascade
"""
