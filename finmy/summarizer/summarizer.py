"""
Codebase used to summarize the main content from the query content.
To preserve the original content, this summarizer avoids any operations based on large language models and relies solely on tools or methods that do not alter or damage the source material.

Both english and chinese are supported.

Support:
    - keywords: Noun words or noun-phrases or fixed combination

"""

import re
import sys
import time
import subprocess
from collections import Counter
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any

import spacy
from spacy.matcher import Matcher
from lmbase.inference import api_call
from langchain_core.prompts import ChatPromptTemplate

from ..generic import UserQueryInput
from ..matcher.utils import safe_parse_json


@dataclass
class SummarizedUserQuery:
    """Summarized user query.

    - `summarization`: text content (required), used for semantic matching/extraction summarized from the user_query.query_text
    - `key_words`: keyword hints (required), summarized from the user_query.query_text if the user_query.key_words are not given.
    - `extras`: extra information (optional), set for backup.
    """

    summarization: str
    key_words: List[str] = field(default_factory=list)

    extras: Dict[str, Any] = field(default_factory=dict)


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


class BaseSummarizer(ABC):
    """Abstract base class for all summarizers."""

    def __init__(
        self,
        config: Optional[dict] = None,
        method_name: Optional[str] = None,
    ):
        self.config = config
        self.method_name = method_name

    @abstractmethod
    def summarize(self, query_input: UserQueryInput) -> SummarizedUserQuery:
        """Produce a summarization from the content.

        Return:
        - List[str]: list of strings, each string is a matched sub-content that may containing one target paragraph (word) or multiple paragraphs (words).
        """

    def invoke_llm(self, messages, llm_name: str) -> str:
        """Invoke the LLM with prepared messages and return raw content."""
        llm = api_call.LangChainAPIInference(lm_name=llm_name)
        resp = llm._inference(messages)
        return resp.response

    def run(self, query_input: UserQueryInput) -> SummarizedUserQuery:
        """End-to-end execution returning a standardized `summarize`."""
        # Compute the time of the whole matching process
        start_time = time.time()
        summarized = self.summarize(query_input)
        end_time = time.time()
        summarized.extras["time_cost"] = end_time - start_time
        return summarized


class KWRuleSummarizer(BaseSummarizer):
    """
    Summarizer the text content by extract all noun as the key words (KW)
    based on rule-based summarization.
    """

    def __init__(self, config):
        super().__init__(config=config, method_name="keywords_summarize")
        # Download necessary NLTK data for English
        self.nlp_en = load_spacy_model("en_core_web_md")
        self.nlp_zh = load_spacy_model("zh_core_web_trf")

    def rule_summarize(self, content: str) -> dict:
        """Extract nouns and noun phrases with frequencies from English or Chinese content. Summarized the content based on the rule.

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
        chinese_chars = len(re.findall(r"[\u4e00-\u9fff]", content))
        total_chars = len(re.findall(r"[\w\u4e00-\u9fff]", content))
        if total_chars > 0 and chinese_chars / total_chars > 0.3:
            doc = self.nlp_zh(content)
            nlp_model = self.nlp_zh
        else:
            doc = self.nlp_en(content)
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

    def summarize(self, query_input: UserQueryInput) -> SummarizedUserQuery:
        """Summarize the user query to obtain the keywords."""
        n_kws = self.rule_summarize(query_input.query_text.strip())
        return SummarizedUserQuery(
            summarization=query_input.query_text,
            key_words=n_kws,
            extras={},
        )


class KWLMSummarizer(BaseSummarizer):
    """LLM-based keyword summarizer.

    Purpose:
    - Extract domain-relevant keywords/key phrases from free text via an LLM.
    - Keep original content unchanged; only produce a keyword list.

    Config:
    - `llm_name`: backend model identifier (default: `deepseek-chat`).

    Output:
    - Returns `SummarizedUserQuery` with `summarization` = original text and
      `key_words` = LLM-extracted keywords. Raw model output is stored in
      `extras["raw"]` for debugging/auditing.
    """

    def __init__(self, config: Optional[dict]):
        super().__init__(config=config, method_name="keywords_summarize_llm")
        self.llm_name = config["llm_name"]

    def _build_messages(self, content: str) -> List[Any]:
        """Build prompts requiring STRICT JSON array of keywords.

        The system prompt guides the model toward noun phrases, entities, and
        domain terms. The human prompt provides the text and a concrete output
        format example to reduce schema deviations.
        """
        system = (
            "You extract concise, informative keywords and key phrases from the given text. "
            "Return ONLY JSON with an array of strings. Focus on noun phrases, named entities, and domain terms."
        )
        human = (
            "Text:\n{content}\n\n"
            'Output strictly in JSON as an array of keywords/phrases. Example: ["market volatility", "risk management"]'
        )
        tmpl = ChatPromptTemplate.from_messages([("system", system), ("human", human)])
        return tmpl.format_messages(content=content)

    def _parse_keywords(self, raw: str) -> List[str]:
        """Normalize LLM output into a clean list of keywords.

        Accepts:
        - JSON array (preferred)
        - JSON object with `keywords` or `key_words`
        - Bare JSON array string
        - Comma-separated fallback
        """
        data = safe_parse_json(raw)
        if isinstance(data, list):
            return [str(x).strip() for x in data if isinstance(x, (str, int, float))]
        if isinstance(data, dict):
            arr = data.get("keywords") or data.get("key_words") or []
            if isinstance(arr, list):
                return [str(x).strip() for x in arr if isinstance(x, (str, int, float))]
        txt = raw.strip()
        if txt.startswith("[") and txt.endswith("]"):
            try:
                arr = safe_parse_json(txt)
                if isinstance(arr, list):
                    return [str(x).strip() for x in arr]
            except Exception:
                pass
        parts = [p.strip() for p in txt.split(",") if p.strip()]
        return parts

    def summarize(self, query_input: UserQueryInput) -> SummarizedUserQuery:
        """End-to-end keyword extraction using the configured LLM.

        Steps:
        1) Build structured prompts demanding JSON array output
        2) Invoke LLM and capture raw content
        3) Parse keywords and return `SummarizedUserQuery`
        """
        content = query_input.query_text.strip()
        messages = self._build_messages(content)
        raw = self.invoke_llm(messages, self.llm_name)
        kws = self._parse_keywords(raw)
        return SummarizedUserQuery(
            summarization=content,
            key_words=kws,
            extras={"raw": raw},
        )
