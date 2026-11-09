"""Local body-language admission; original bytes and paragraph offsets stay intact."""
from functools import lru_cache


@lru_cache(maxsize=1)
def _detector():
    from langid.langid import LanguageIdentifier, model
    # Keep all languages enabled: restricting the classifier to en/zh would
    # falsely classify every Russian/French document as an allowed language.
    return LanguageIdentifier.from_modelstring(model, norm_probs=True)


@lru_cache(maxsize=512)
def detect(text):
    if not any(char.isalpha() for char in text):
        return 'unknown'
    return _detector().classify(text)[0]


def assess(document, allowed):
    if not allowed:
        return {'allowed': True, 'languages': [], 'policy': 'unrestricted'}
    text = '\n\n'.join(row['text'] for row in document['blocks'])
    # Inspect beginning, middle and end, rather than trusting title, URL or
    # English company names in an otherwise foreign-language article.
    starts = sorted({0, max(0, len(text)//2-2000), max(0, len(text)-4000)})
    languages = list(dict.fromkeys(detect(text[start:start+4000]) for start in starts))
    return {'allowed': bool(languages) and all(lang in allowed for lang in languages),
            'languages': languages, 'policy': 'body_language',
            'reason': 'Only configured source languages are admitted'}
