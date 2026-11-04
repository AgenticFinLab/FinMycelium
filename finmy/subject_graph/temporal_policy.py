"""Calendar normalization and temporal reasoning for subject histories."""

TEMPORAL_NORMALIZATION_POLICY = """
Temporal normalization policy (applies to all reconstructed time fields):
- Recognize temporal expressions across languages, calendar systems, era-based year numbering, and regional or historical conventions, including calendar dates, festivals, solar terms, seasons, reporting periods, fiscal periods, relative dates, and business/trading days. These categories are illustrative, not an exhaustive whitelist.
- Identify the original expression and its supported calendar, year-numbering system, reference year/event, locale, and timezone before conversion. Distinguish calendar conversion from year-number conversion; account for applicable year starts, leap rules, and historical conventions rather than assuming a fixed year offset. Source language alone does not establish a calendar or locale.
- Normalize to Gregorian dates or ranges at the finest precision justified jointly by Content and a reliably established, applicable calendar rule. A date derived by such a rule need not appear literally in Content. Resolve aliases from context; if the calendar, anchor, or conversion rule remains ambiguous, retain supported coarse information or mark the unresolved boundary as "unknown" rather than guess.
- Preserve the original source wording in existing evidence_source_contents. In existing reasons, distinguish directly stated values from derived values and explain the anchor, applicable convention/rule, and remaining uncertainty. Use supplied reference information or available calculation tools when needed; if a conversion cannot be established reliably, leave it unresolved. Do not claim external verification or tool use that did not occur.
- For periods, derive bounds only from supported context or an explicitly applicable convention. Distinguish a named day from a holiday period, calendar from fiscal periods, and elapsed days from business/trading days. In reasons, distinguish an occurrence window from evidence that an activity lasted throughout that window. Do not choose a midpoint or arbitrary endpoint as the occurrence date.
- Use only existing Schema fields. Where start_time/end_time exist, put supported bounds in those fields separately. For a single timestamp field, use a supported exact or coarse Gregorian value; if the range cannot be represented faithfully, use "unknown" and describe the supported range in its existing reasons. Do not add fields or encode a combined range string as a timestamp.
- Supported output precision is YYYY, YYYY-MM, YYYY-MM-DD, YYYY-MM-DD HH:MM, or YYYY-MM-DD HH:MM:SS, with an evidenced timezone when applicable. Retain year/month precision when no valid rule supports finer precision; never pad it with an invented month, day, or midnight. After calendar conversion, a source period may cross Gregorian months or years, so represent its actual supported bounds rather than forcing it into one Gregorian year/month.
- Keep occurrence, publication, filing, and disclosure times distinct. Resolve relative expressions against the appropriate source/event anchor, not the current run date. Time normalization does not establish episode membership or justify moving an activity into a different Episode.

"""

SUBJECT_TEMPORAL_POLICY = """
Temporal reasoning for subject histories:
- Native SubjectGraph supports optional time_window on a time VerifiableField:
  {"start": "2022-07-21", "end": "2022-07-31", "original": "2022年7月下旬",
   "approximate": true}. This overrides the shared single-timestamp fallback to unknown.
  Normalize ordinary natural dates using their source context and calendar convention.
  Keep the source phrase in original and exact supporting text in evidence_source_contents.
  For an imprecise date, store the usable bounds in time_window and set approximate=true;
  value may use the supported year/month or a positioning boundary. For a named exact
  day, use equal bounds and approximate=false. Derive the year from the source context.
  Use the same format for event bounds, participation dates, actions and transactions.
  Unknown is reserved for dates whose range genuinely cannot be resolved. Do not hide
  an understood interval only in reasons. No candidate-date lists or extra search.
  For Chinese month periods, 上旬=1–10, 中旬=11–20, 下旬=21–month end; apply leap years.
  Other natural periods and calendar conversions use their applicable general rule.
  Calendar conversion alone does not make an exact named day approximate.
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
  interval cannot fit a single timestamp, preserve it in time_window as described
  below. Do not broaden to an arbitrary year.
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
