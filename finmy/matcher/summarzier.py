"""
Codebase used to summarize the main content from the query content.
To preserve the original content, this summarizer avoids any operations based on large language models and relies solely on tools or methods that do not alter or damage the source material.

Both english and chinese are supported.

Support:
    - keywords: Noun words or noun-phrases or fixed combination

"""

import re
import sys
import subprocess
from collections import Counter

import spacy
from spacy.matcher import Matcher


def load_spacy_model(model_name: str):
    """
    Attempts to load a spaCy model. If it fails, downloads it automatically.
    """
    try:
        nlp = spacy.load(model_name)
        print(f"Successfully loaded spaCy model: {model_name}")
        return nlp
    except OSError:
        print(f"spaCy model '{model_name}' not found. Attempting to download...")
        try:
            # Use subprocess to run the spacy download command
            subprocess.check_call(
                [sys.executable, "-m", "spacy", "download", model_name]
            )
            nlp = spacy.load(model_name)
            return nlp
        except subprocess.CalledProcessError as e:
            print(f"Failed to download spaCy model '{model_name}'. Error: {e}")
            raise
        except Exception as e:
            print(
                f"An unexpected error occurred while loading/downloading '{model_name}': {e}"
            )
            raise


class NounKeyWordSummarizer:
    """
    Summarizer the text content by extract all noun as the key words.
    """

    def __init__(self):
        # Download necessary NLTK data for English
        self.nlp_en = load_spacy_model("en_core_web_md")
        self.nlp_zh = load_spacy_model("zh_core_web_trf")

    def extract_nouns_with_frequency(self, text: str) -> dict:
        """Extract nouns and noun phrases with frequencies from English or Chinese text.

        Overview:
        - Language detection: use CJK character ratio to select the spaCy pipeline.
        - Entities first: add full named entity spans (high-value phrases).
        - Noun chunks: add dependency-based noun phrases and normalize them.
        - Matcher: capture compound noun patterns and short ADJ+NOUN phrases; normalize spans
          by stripping leading determiners and most adjectives. Retain canonical ADJ+NOUN when
          the adjective is an attributive modifier immediately before the noun.
        - Fallback nouns: include standalone nouns not covered by any span.
        - Normalization: English phrases lowercased; English tokens use lemma; Chinese phrases
          concatenated without spaces to avoid gaps.
        """
        # Lightweight language detection using Unicode ranges.
        chinese_chars = len(re.findall(r"[\u4e00-\u9fff]", text))
        total_chars = len(re.findall(r"[\w\u4e00-\u9fff]", text))
        if total_chars > 0 and chinese_chars / total_chars > 0.3:
            doc = self.nlp_zh(text)
            nlp_model = self.nlp_zh
        else:
            doc = self.nlp_en(text)
            nlp_model = self.nlp_en
        is_en = nlp_model == self.nlp_en

        # Accumulator for extracted terms/phrases.
        all_terms = []
        # 1) Named entities: keep full surface form.
        entity_spans = list(doc.ents)
        for ent in entity_spans:
            all_terms.append(ent.text.strip())

        noun_chunk_spans = []
        try:
            noun_chunk_spans = list(doc.noun_chunks)
        except Exception:
            # Some models may not expose noun_chunks; fail gracefully.
            noun_chunk_spans = []

        def strip_leading_adj_det(span):
            tokens = [t for t in span]
            if not tokens:
                return ""
            if is_en:
                has_det = any(t.pos_ == "DET" for t in tokens)
                if tokens[0].pos_ == "ADJ":
                    adj_is_amod = tokens[0].dep_ == "amod"
                    second_is_noun = len(tokens) > 1 and tokens[1].pos_ in (
                        "NOUN",
                        "PROPN",
                    )
                    short_chunk = len(tokens) <= 3
                    if adj_is_amod and second_is_noun and not has_det and short_chunk:
                        return " ".join(t.text for t in tokens).strip().lower()
            i = 0
            while i < len(tokens) and tokens[i].pos_ in ("ADJ", "DET"):
                i += 1
            kept = tokens[i:]
            if not kept:
                return ""
            if is_en:
                return " ".join(t.text for t in kept).strip().lower()
            else:
                return "".join(t.text for t in kept).strip()

        for chunk in noun_chunk_spans:
            phrase = strip_leading_adj_det(chunk)
            if phrase:
                all_terms.append(phrase)

        # 3) Matcher rules: compound nouns and short adjective-led noun phrases
        matcher = Matcher(nlp_model.vocab)
        matcher.add(
            "COMPOUND_NP",
            [
                # Two-word compound (e.g., "risk management", "market volatility")
                [
                    {"POS": {"IN": ["PROPN", "NOUN"]}},
                    {"POS": {"IN": ["PROPN", "NOUN"]}},
                ],
                # Three-word compound (e.g., "supply chain risk")
                [
                    {"POS": {"IN": ["PROPN", "NOUN"]}},
                    {"POS": {"IN": ["PROPN", "NOUN"]}},
                    {"POS": {"IN": ["PROPN", "NOUN"]}},
                ],
                # ADJ + NOUN (e.g., "artificial intelligence")
                [
                    {"POS": "ADJ"},
                    {"POS": {"IN": ["PROPN", "NOUN"]}},
                ],
                # ADJ + NOUN + NOUN (e.g., "financial market risk")
                [
                    {"POS": "ADJ"},
                    {"POS": {"IN": ["PROPN", "NOUN"]}},
                    {"POS": {"IN": ["PROPN", "NOUN"]}},
                ],
            ],
        )
        # Normalize matched spans and collect phrases.
        matched_spans = []
        for match_id, start, end in matcher(doc):
            span = doc[start:end]
            matched_spans.append(span)
            phrase = strip_leading_adj_det(span)
            if phrase:
                all_terms.append(phrase)

        # Helper: check if a token is covered by any collected span.
        def in_any_span(token):
            for s in entity_spans:
                if token.idx >= s.start_char and token.idx < s.end_char:
                    return True
            for s in noun_chunk_spans:
                if token.idx >= s.start_char and token.idx < s.end_char:
                    return True
            for s in matched_spans:
                if token.idx >= s.start_char and token.idx < s.end_char:
                    return True
            return False

        # 4) Fallback: standalone nouns not already included in any span.
        for token in doc:
            if (
                (token.pos_ in ["NOUN", "PROPN"])
                and not token.is_punct
                and not token.is_space
            ):
                if not in_any_span(token):
                    term = token.lemma_.lower() if is_en else token.text
                    if term.strip():
                        all_terms.append(term)

        # Aggregate term frequencies.
        freq_counter = Counter(term for term in all_terms if term.strip() != "")
        return dict(freq_counter)
