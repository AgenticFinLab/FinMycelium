"""
A session to test the `finmy/matcher/summarizer`

Run:
    python examples/uTEST/Matcher/test_summary.py
"""

from dotenv import load_dotenv

from finmy.summarizer.summarizer import KWLMSummarizer
from finmy.generic import UserQueryInput

load_dotenv()

if __name__ == "__main__":

    # Create extractor instance
    summarizer = KWLMSummarizer(config={"llm_name": "deepseek/deepseek-chat"})

    # User query input demo
    query_input = UserQueryInput(
        query_text="Natural language processing is a fascinating field of artificial intelligence.",
        key_words=["natural language processing", "artificial intelligence"],
    )

    # Summarize the user query
    summarized_query = summarizer.summarize(query_input)
    print("Summarized query:")
    print(summarized_query)
