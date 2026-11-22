# Search-only evaluation

From the repository root, with the existing project environment and .env:

    python -m finmy.search.eval --task examples/search_eval/buffett_goldman.json

The bundled example preserves the confirmed Buffett/Goldman event scope.
Pass your own task JSON path in the same way.

The task JSON is the same research task object used by the search pipeline:
target_type, target_name, query_text, and optional key_words, seed_urls,
catalog and research_scope. Keep catalog.kind=person_event for person events.
There is no required model, task ID, output-directory or execute flag.

The command runs Workbench's existing enhanced-search coordinator and then
evaluates the saved originals using Kimi. Search tools, prompts, reading,
selection and budgets are unchanged. This CLI defaults both search and Judge
to ark/kimi-k3-1-pro-261024 with low reasoning effort; ordinary Workbench
defaults remain unchanged. The search output limit is 8,192 tokens.
An optional --config path accepts an existing SearchConfig JSON or YAML when
matching a particular Workbench run's model and limits.

The default providers are Baidu, Bocha and Exa. The command loads the repository
.env without overriding exported variables. Existing ARK_API_KEY,
BAIDUSEARCH_API_KEY, BOCHA_API_KEY and EXA_API_KEY entries are used.
It stops after search and evaluation; no extraction, graph construction or
Builder entry point is called.

## Output and resume

The combined report is:

    output/search-eval/eval-<task-config-code-hash>/output.json

It contains the complete task/configuration, candidate source metadata,
original text and source locations for the acquired reference pool, the exact
final search material, selection records, Judge rubric and labels, metrics,
token usage and timings. The existing search state/raw responses remain beside
it under runs/initial and sources. Judge requests, responses and cache records
are saved under judge.

Use --output path.json to choose a different combined report filename.
Repeat the same command to reuse finished search work and validated Judge
answers. Completed Judge batches survive a later failure. --fresh creates a
separate run for another trial. Search configuration or search code changes
create a separate task identity, including uncommitted algorithm edits.
A search that has not reached finished/insufficient saves its
output and exits with code 2, without starting the Judge.

## What the metrics measure

The Judge first derives up to eight evidence questions from the task, then labels
all usable acquired originals, including unread and excluded sources. It does
not see which material the search selected or its rank. Evaluation-only windows
carry original offsets and nearby context; they never change search chunks.
Grade 0 means irrelevant/mismatched, 1 useful context, and 2 direct support.
Grade 2 requires exact original quotations tied to a question; invalid IDs,
quotes, grades and incomplete batches are rejected and retried once.

- Provider result lists: Precision, Recall, nDCG, AP, reciprocal rank and hit
  rate at 1, 3, 5 and 10. Macro AP is MAP. These use the actual per-provider,
  per-query order and the overall task's relevance judgments. A short list is
  padded with misses for Precision@k. The source grade is its maximum window
  grade. nDCG's gain is 2**grade-1.
- Final delivered material: useful/direct-evidence character fractions,
  entity/event/attribute/scope mismatch rate, retained evidence-quote coverage,
  question coverage, and exact text duplication. Identical quote/question
  pairs across reposts count once for quote coverage.
- Usage: search and Judge calls/tokens separately, cache tokens as a subset of
  input tokens, provider/read/model timings and invocation wall time. Provider
  billing prices are not inferred from token counts.

Recall is relative to the acquired, judged source pool. Unfetched URLs and
failed parses have unknown relevance; they are not negative examples.
Rank metrics for lists containing unknown top-k bodies are null, with judgment
coverage and the excluded-list count available. Empty relevance denominators
are also null. Final material has no global relevance ordering, so the report
does not manufacture a global nDCG from file order. These are single-task
baseline metrics; use held-out tasks and the same budget/configuration when
comparing algorithm versions.

For a frozen comparison across runs, pool the acquired originals and reuse one
set of judgments; independently built reference pools are not interchangeable.

## Offline verification

    python -m pytest -q tests/test_search_eval.py

The tests inject search/model transports, forbid network access and Builder
imports, exercise the real search coordinator, check metric arithmetic,
retained quote offsets, unknown candidates, failed judgments and cache reuse.
