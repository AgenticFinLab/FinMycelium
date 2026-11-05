"""Evidence remains readable and safe in the existing Plotly hover surface."""
from html import escape
from html.parser import HTMLParser
import copy

from finmy.subject_graph.gantt_hover import (
    event_hover, episode_hover, field_hover, fields_hover, participant_hover, provenance_hover, relation_hover,
)


def visible_text(markup):
    class Text(HTMLParser):
        def __init__(self):
            super().__init__()
            self.parts = []

        def handle_data(self, data):
            self.parts.append(data)

    parser = Text()
    parser.feed(markup)
    return "".join(parser.parts)


def test_flagged_field_retains_review_state_confidence_and_evidence():
    field = {"value": "Responded on succession", "evidence_status": "needs_review",
             "confidence": None, "reasons": ["Reported in the source."],
             "evidence_source_contents": ["The quoted response still needs review."]}
    html = field_hover(field, "Action")
    assert "<b>Needs review</b>" in html
    assert html.index("Needs review") < html.index("Responded on succession")
    assert "Confidence: unknown" in html
    assert "Reported in the source." in html
    assert "The quoted response still needs review." in html


def test_raw_and_escaped_text_are_safe_without_double_escaping():
    value = '<img src=x onerror="alert(1)"> & comparison'
    raw = field_hover({"value": value})
    encoded = field_hover({"value": escape(value)})
    assert raw == encoded
    assert "<img" not in raw
    assert visible_text(raw) == value


def test_long_evidence_is_wrapped_without_truncation_and_duplicates_are_shared():
    quote = 'Original  source: A&B <value> ' + ('long passage with detail; ' * 30)
    fields = [{"value": "Claim one", "confidence": 0.0,
               "reasons": ["Same basis", "Same basis"], "evidence_source_contents": [quote]},
              {"value": "Claim two", "confidence": 0.95,
               "reasons": ["Same basis"], "evidence_source_contents": [escape(quote)]}]
    html = fields_hover(fields)
    text = visible_text(html)
    assert quote in text
    assert text.count(quote) == 1
    assert text.count("Same basis") == 1
    assert "Confidence: 0.0" in text
    assert "Confidence: 0.95" in text
    assert html.count("<br>") > 10


def test_original_time_and_approximate_window_are_kept():
    field = {"value": "2022-07-21", "time_window": {
        "original": "2022年7月下旬", "start": "2022-07-21", "end": "2022-07-31",
        "approximate": True}}
    text = visible_text(field_hover(field, "Time"))
    assert "Original time: 2022年7月下旬（约）" in text
    assert "Time window: 2022-07-21 — 2022-07-31 (approximate)" in text
    assert "发生于该范围内，具体日期不详。" in text
    assert fields_hover([]) == ""


def vf(value):
    return {"value": value, "evidence_source_contents": ["Shared source excerpt."],
            "reasons": ["Shared basis."], "confidence": 0.9}


def test_transaction_hover_resolves_parties_and_keeps_unknown_and_evidence():
    transaction = {"name": vf("Buy shares"), "from_entity_id": vf("unknown"),
                   "to_entity_id": vf("org_a"), "timestamp": vf("2022-07"),
                   "instruments": [vf("Ordinary shares")], "details": [vf("Bought 100 shares.")]}
    original = copy.deepcopy(transaction)
    text = visible_text(episode_hover({"kind": "transaction", "transaction": transaction,
                                      "names": {"org_a": "Company A"}}))
    for expected in ("Transaction: Buy shares", "From: unknown", "To: Company A",
                     "Time: 2022-07", "Instrument: Ordinary shares", "Bought 100 shares."):
        assert expected in text
    assert text.count("Shared source excerpt.") == 1
    assert transaction == original


def test_participant_hover_preserves_aliases_participation_and_global_relation():
    entity = {"entity_id": "person_a", "name": vf("Person A"), "entity_type": "individual",
              "aliases": ["别名"], "attributes": {"Occupation": vf("Investor")}}
    relation = {"from_entity_id": "org_a", "to_entity_id": "person_a",
                "relation_type": vf("employs"), "valid_from": vf("2022"), "valid_to": vf("unknown")}
    metadata = {"entity": entity, "participations": [{"role": vf("Speaker"),
                "start_time": vf("2023-05-06"), "end_time": vf("2023-05-06")}],
                "overview": [vf("Person overview")], "action_names": [vf("Spoke")],
                "global_relations": [relation], "names": {"org_a": "Company A", "person_a": "Person A"}}
    original = copy.deepcopy(metadata)
    text = visible_text(participant_hover(metadata))
    for expected in ("Aliases: 别名", "Occupation: Investor", "Role: Speaker", "Person overview",
                     "Participation start: 2023-05-06", "Action: Spoke",
                     "Company A — employs → Person A", "Valid from: 2022", "Valid to: unknown"):
        assert expected in text
    assert metadata == original
    metadata["participations"] = []
    text = visible_text(participant_hover(metadata))
    assert "Contextual entity" in text
    assert "Participation start:" not in text


def test_event_action_and_relation_hover_preserve_native_status_and_time():
    event = {"title": vf("Meeting"), "start_time": vf("2023-05"), "end_time": vf("2023-05"),
             "descriptions": [vf("Market conditions")], "subject_relevance": vf("Person spoke")}
    assert "Market conditions" in visible_text(event_hover(event))
    action = {"action_type": {**vf("Discussed succession"), "evidence_status": "needs_review"},
              "timestamp": vf("unknown"), "details": [vf("Explained the succession plan.")]}
    text = visible_text(episode_hover({"kind": "action", "action": action}))
    assert "Needs review" in text and "Time: unknown" in text
    relation = {"relation_type": vf("Partner"), "valid_from": vf("unknown"), "valid_to": vf("2023")}
    text = visible_text(relation_hover({"relation": relation, "contextual": True}))
    assert "Contextual relation" in text
    assert "Valid from: unknown" in text and "Valid to: 2023" in text


def test_values_and_sources_are_preserved_across_existing_hovers():
    entity = {"entity_id": "person_a", "name": vf("Person A"), "entity_type": "individual",
              "aliases": [], "attributes": {}}
    action = {"action_type": {**vf("Explained a choice"), "evidence_status": "needs_review"},
              "timestamp": vf("2023-05"), "details": [vf("A complete decision explanation.")]}
    bar = visible_text(episode_hover({"kind": "action", "action": action}))
    node = visible_text(participant_hover({"entity": entity, "participations": [], "actions": [action]}))
    assert "A complete decision explanation." in bar
    assert "A complete decision explanation." not in node
    assert "Shared source excerpt." not in bar
    assert "Shared source excerpt." in node
    assert "Needs review" in bar and "Needs review" in node
    assert "Confidence: 0.9" in bar
    event = {"title": vf("Meeting"), "start_time": vf("2023-05"), "end_time": vf("2023-05"),
             "descriptions": [vf("Market conditions")], "subject_relevance": vf("Person spoke")}
    event_bar = visible_text(event_hover(event))
    context_bar = visible_text(episode_hover({"kind": "context", "event": event}))
    assert "Market conditions" in event_bar
    assert "Shared source excerpt." not in event_bar
    assert "Shared source excerpt." in context_bar
    assert "Market conditions" not in context_bar


def test_transaction_sources_use_node_when_available_and_fall_back_to_bar():
    transaction = {"name": vf("Buy shares"), "from_entity_id": vf("unknown"),
                   "to_entity_id": vf("org_a"), "timestamp": vf("2022-07"),
                   "instruments": [vf("Ordinary shares")], "details": [vf("Bought 100 shares.")]}
    names = {"org_a": "Company A"}
    metadata = {"kind": "transaction", "transaction": transaction, "names": names,
                "provenance_on_node": True}
    entity = {"entity_id": "org_a", "name": vf("Company A"), "entity_type": "organization",
              "aliases": [], "attributes": {}}
    bar = visible_text(episode_hover(metadata))
    node = visible_text(participant_hover({"entity": entity, "participations": [],
                                          "transaction": transaction, "names": names}))
    assert "Bought 100 shares." in bar and "Bought 100 shares." not in node
    assert "Shared source excerpt." not in bar and "Shared source excerpt." in node
    metadata["provenance_on_node"] = False
    assert "Shared source excerpt." in visible_text(episode_hover(metadata))
    assert "Buy shares" not in visible_text(provenance_hover([transaction["name"]]))
