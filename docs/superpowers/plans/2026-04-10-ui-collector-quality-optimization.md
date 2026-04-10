# UI Collector Quality Optimization Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make UI search collection faster and cleaner by adding configurable domain filtering, ranking, and parse budgets before URL parsing.

**Architecture:** Keep the current UI pipeline intact and concentrate all behavior changes inside `DataCollectorService`. Add configuration-driven candidate selection before per-result parsing, and prove the behavior with isolated unit tests.

**Tech Stack:** Python, unittest, Streamlit service layer, YAML configuration

---

### File Map

**Modify**
- `finmy/web_ui/services/data_collector_service.py`
- `configs/pipline.yml`
- `tests/test_web_ui_input_handling.py`

**Keep as-is**
- `finmy/web_ui/services/reconstruction_service.py`
- `finmy/builder/...`

### Task 1: Lock In Candidate Selection Rules With Tests

**Files:**
- Modify: `tests/test_web_ui_input_handling.py`
- Test: `tests/test_web_ui_input_handling.py`

- [ ] **Step 1: Add failing tests for filtering, ranking, and parse limits**

Add tests that express these rules:

```python
def test_collect_bocha_search_results_skips_blocked_domains(self):
    ...

def test_collect_baidu_search_results_prefers_configured_domains_before_parsing(self):
    ...

def test_collect_baidu_search_results_respects_parse_limit_after_filtering(self):
    ...
```

- [ ] **Step 2: Run tests to verify failure**

Run:

```bash
cd /home/lenovo/projects/AgenticFinLab/FinMycelium
python3 -m unittest tests.test_web_ui_input_handling -v
```

Expected: new tests fail because the service still parses blocked and over-budget results.

- [ ] **Step 3: Commit the red test state only if useful locally; otherwise proceed without commit**

No commit required here if the branch already contains uncommitted UI fixes.

### Task 2: Implement Configurable Candidate Selection

**Files:**
- Modify: `finmy/web_ui/services/data_collector_service.py`
- Modify: `configs/pipline.yml`
- Test: `tests/test_web_ui_input_handling.py`

- [ ] **Step 1: Add config-backed selection helpers**

Implement small helpers in `DataCollectorService` for:

```python
def _hostname(self, url: str) -> str: ...
def _is_blocked_domain(self, url: str) -> bool: ...
def _preferred_rank(self, url: str) -> int: ...
def _select_candidates(self, items: List[dict], parse_limit: int) -> List[dict]: ...
```

- [ ] **Step 2: Wire Bocha collection through the selector**

Update `collect_bocha_search_results()` so it:

```python
bocha_search_count = collector_cfg.get("bocha_search_count", 10)
bocha_parse_limit = collector_cfg.get("bocha_parse_limit", 6)
results = bochasearch_api(search_query, summary=True, count=bocha_search_count)
selected_items = self._select_candidates(raw_items, bocha_parse_limit)
```

- [ ] **Step 3: Wire Baidu collection through the selector**

Update `collect_baidu_search_results()` so it:

```python
baidu_parse_limit = collector_cfg.get("baidu_parse_limit", 8)
selected_items = self._select_candidates(raw_references, baidu_parse_limit)
```

- [ ] **Step 4: Add safe quality defaults to YAML**

Add entries under `url_collector_config` like:

```yaml
  bocha_search_count: 10
  bocha_parse_limit: 5
  baidu_parse_limit: 8
  blocked_domains:
    - "wordhippo.com"
    - "docin.com"
    - "book118.com"
    - "taodocs.com"
    - "dictall.com"
    - "chashiwen.com"
    - "edudba.com"
    - "iask.sina.com.cn"
  preferred_domains:
    - "cnn.com"
    - "theguardian.com"
    - "cps.gov.uk"
    - "baike.baidu.com"
    - "163.com"
    - "weixin.qq.com"
    - "weibo.com"
```

- [ ] **Step 5: Run tests to verify pass**

Run:

```bash
cd /home/lenovo/projects/AgenticFinLab/FinMycelium
python3 -m unittest tests.test_web_ui_input_handling -v
```

Expected: all UI input-handling tests pass.

- [ ] **Step 6: Commit implementation**

```bash
cd /home/lenovo/projects/AgenticFinLab/FinMycelium
git add finmy/web_ui/services/data_collector_service.py configs/pipline.yml tests/test_web_ui_input_handling.py
git commit -m "fix: filter noisy UI search results before parsing"
```

### Task 3: Sanity-Check UI Runtime Inputs

**Files:**
- Modify: `tests/test_web_ui_input_handling.py`

- [ ] **Step 1: Add one regression test for phrase-preserving keywords + filtered parsing**

Add a test that combines:

```python
keywords = parse_keywords("fraud,money laundering,Qian Zhimin")
assert keywords == ["fraud", "money laundering", "Qian Zhimin"]
```

with a search fixture containing both preferred and blocked domains.

- [ ] **Step 2: Run the focused suite again**

Run:

```bash
cd /home/lenovo/projects/AgenticFinLab/FinMycelium
python3 -m unittest tests.test_web_ui_input_handling -v
```

Expected: pass.

- [ ] **Step 3: Commit regression coverage**

```bash
cd /home/lenovo/projects/AgenticFinLab/FinMycelium
git add tests/test_web_ui_input_handling.py
git commit -m "test: cover phrase keywords with filtered UI search"
```

### Task 4: Manual UI Verification Handoff

**Files:**
- No code changes required

- [ ] **Step 1: Hand off a stable UI rerun command**

Use:

```bash
cd /home/lenovo/projects/AgenticFinLab/FinMycelium
source /home/lenovo/projects/AgenticFinLab/.venv/bin/activate
streamlit run examples/uTEST/test_web_interface.py
```

- [ ] **Step 2: Hand off controlled UI inputs**

Use:

```text
Main Input:
What is the case involving fraud and money laundering by Qian Zhimin?

Keywords:
fraud,money laundering,Qian Zhimin
```

- [ ] **Step 3: Capture manual verification outputs**

Ask the user to report:

- Bocha parse duration
- Baidu parse duration
- whether blocked low-quality domains disappeared
- whether builder now gets fewer, cleaner samples

