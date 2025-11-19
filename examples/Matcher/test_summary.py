"""
A session to test the `finmy/matcher/summarizer`
"""

from finmy.matcher import summarzier


if __name__ == "__main__":

    # Create extractor instance
    extractor = summarzier.NounKeyWordSummarizer()

    # English text demo
    english_text = """
    Natural language processing is a fascinating field of artificial intelligence. 
    Machine learning algorithms can analyze text data effectively. 
    The University of California has excellent research programs in computer science. 
    Apple Inc. develops innovative technologies for consumers worldwide. 
    New York is a major city in the United States with diverse cultural attractions.
    Natural language processing is very important in artificial intelligence.
    """

    print("English text:")
    print(english_text)
    english_nouns_freq = extractor.extract_nouns_with_frequency(english_text)
    print("Extracted nouns and noun phrases with frequencies:")
    for noun, freq in english_nouns_freq.items():
        print(f"'{noun}': {freq}")
    print(f"Total {len(english_nouns_freq)} unique items\n")

    # Chinese text demo
    chinese_text = """
    自然语言处理是人工智能领域的一个迷人分支。
    机器学习算法能够有效地分析文本数据。
    加州大学拥有优秀的计算机科学研究项目。
    苹果公司为全球消费者开发创新技术。
    纽约是美国的一个主要城市，拥有丰富的文化景观。
    人工智能技术正在改变我们的生活方式。
    自然语言处理在人工智能中非常重要。
    """

    print("Chinese text:")
    print(chinese_text)
    chinese_nouns_freq = extractor.extract_nouns_with_frequency(chinese_text)
    print("Extracted nouns and noun phrases with frequencies:")
    for noun, freq in chinese_nouns_freq.items():
        print(f"'{noun}': {freq}")
    print(f"Total {len(chinese_nouns_freq)} unique items\n")

    # Mixed text demo
    mixed_text = """
    自然语言处理Natural Language Processing是人工智能Artificial Intelligence的重要分支。
    机器学习Machine Learning算法可以分析文本text数据。
    自然语言处理Natural Language Processing技术很重要。
    """

    print("Mixed text (Chinese + English):")
    print(mixed_text)
    mixed_nouns_freq = extractor.extract_nouns_with_frequency(mixed_text)
    print("Extracted nouns and noun phrases with frequencies:")
    for noun, freq in mixed_nouns_freq.items():
        print(f"'{noun}': {freq}")
    print(f"Total {len(mixed_nouns_freq)} unique items\n")
