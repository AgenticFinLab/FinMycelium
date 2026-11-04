"""Subject-specific temporal reasoning, extending the shared calendar policy."""

SUBJECT_TEMPORAL_POLICY = """
Temporal reasoning for subject histories:
- Apply the shared calendar policy to ordinary named dates and periods; do not mark
  a date unknown merely because the source uses natural language. For example,
  Christmas Day 2022 is 2022-12-25 under the established Gregorian convention.
  Spring 2022 can use March-May under an applicable northern meteorological
  convention; this is a seasonal window, not an exact day or continuous activity.
  Preserve the source phrase and explain the rule in reasons. Do not silently apply
  that convention to a southern, astronomical, fiscal or holiday-period context.
- A quarter-end holding snapshot establishes a position at that date, not a purchase
  on that date. For a purchase known only to calendar Q3, use July-September event
  bounds. Do not assign September 30 to its action timestamp. If its supported
  interval cannot fit the existing single timestamp field, retain unknown there
  and the actual supported interval in reasons. Do not broaden to an arbitrary year.
- Separate when an act occurred, when its information became available, and when a
  later source reported or explained it. A later source may establish an earlier
  act, but its later prices, results and commentary are not earlier decision inputs.
  A November price cannot explain a Q3 purchase as information available at purchase.
  Keep supported later observations explicitly dated as later context, or omit the
  unsupported causal connection. Public availability alone does not prove knowledge.
- A later explanation is an action on the explanation date. Earlier trade dates
  belong in its details; do not move the explanation into the trade's interval.
  Relative dates use the source passage's own anchor, never the run date or a
  convenient target-event year. A report's reference year is not its publication year.
- Repeated reports of one occurrence remain one event. In particular, a letter named
  for a financial year and the same letter named for its next-year publication are
  one publication when the source context identifies them as such. Merge complementary
  details without treating recurring annual meetings or merely similar topics as one.
- Keep uncertain personal attribution uncertain in action_type and details as well
  as reasons. An observer's inference from position size or a person's job title
  cannot become a definite personal decision. Retain the company's supported act
  and the qualified observation; preserve a personal decision only with evidence.
"""
