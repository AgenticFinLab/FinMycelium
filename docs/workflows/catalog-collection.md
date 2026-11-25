# Catalog collection and withdrawal

Collection is an explicit workbench action, separate from retrieval, construction
and content review. It does not start a model or search request.

## Confirm search material

In a catalog-linked search task, open **确认交接与收录**, check the actual handoff
and known gaps, enter the confirmer and choose **确认并收录检索材料**. No build task
is required. The event's `search/` contains:

- `builder-input.json`: exact confirmed payload, including the original passages.
- `sources.csv`: sources in that payload.
- `search-summary.md`: scope, usage and known gaps.
- `manifest.json`: search task, handoff revision, source versions and hashes.

Person input uses the same adapter as build creation. Ordinary event material
still goes through the existing evidence review before an Agent/Sparse build.
Saving a confirmed build continues to collect its actual input for compatibility.
Reassembly or rerunning search does not silently replace a collected version.
A subsequent explicit confirmation can replace it; prior task inputs remain fixed.

**材料已收录** means the current handoff has an intact catalog collection.
**已确认用于构建** identifies a handoff already bound to a saved build, even if its
catalog copy is later withdrawn. These facts do not imply graph acceptance.

## Select a person Event draft for content review

In **数据集 → 人物事件**, select the person, storyline and Event. **检索材料** shows the
collected sources, gaps, and frozen input. **用已收录材料创建构建** saves a ready
task using that exact input and receipt. The original search runtime is optional.
Older collections that contain only a source list and summary can be inspected
through their original search task.

Under **事件图**, compare completed drafts by their actual frozen input. One
search task can produce several handoff revisions. The workbench labels drafts
that use the current material and also allows an earlier version to be selected.
For a build with supplemental passages, the collected handoff identifies the original
material. The review bundle includes the complete `input.json` used for that graph,
with the additional passages and its own hash.
Choose a draft and click **将此版本送审**. **改送此版本** replaces the pending choice.
**撤回送审** returns the event to the pool of available drafts.

Open **任务中心 → 待处理** and select **图审核** to find a nominated person draft. Each person event has at most one pending version. Its shared record lives at
`workbench/review/<person_id>/<storyline_id>/<event_id>.json` and binds the build
ID to the graph, Gantt and frozen input hashes. On the machine holding the build,
**下载审核包** provides those three files and a pending `review.md` template.
Teammates can review that ZIP on another machine. Submit the completed review
in the build task on the machine holding the original artifacts. Collection and
discard remove the pending choice. All other experiments remain in task history.

## Discard a draft

After a build stops, **草稿采用选择 → 舍弃本次草稿** records the reason and marks
the task **已舍弃**. The execution/result status, files and usage are preserved.
**恢复待审核** reverses that selection without restarting construction. Discarded
person drafts cannot be collected or resumed until restored. Withdraw an accepted
graph first if it must then be discarded.

## Collect a reviewed person Event

1. From a completed draft, download **本图审核记录模板**. Review the graph and
   evidence outside the interface and complete `review.md`. The unified content
   review Skill remains separate work; the template is a binding record, not an
   automatic content audit.
2. Upload the completed record and explicitly confirm collection. The YAML header
   binds `event_id`, `build_task_id`, `graph_sha256`, `input_sha256`, and
   `gantt_sha256`; complete `reviewer`, `reviewed_at` and `decision: accepted`.
   The body records findings, remaining uncertainties and the acceptance conclusion.
3. The workbench verifies the frozen input, draft/checks/Gantt bindings, catalog
   identity and review. It copies the exact `epg.json`, `gantt.html`, `review.md`
   to the event's `epg/`, then sets `events.csv` to `accepted` with relative paths.

Refresh derives **已收录** and download links from intact files, review bindings,
the current task's graph/input hashes and the matching catalog row. The same
recognition works for a correctly bound collection made outside the interface.
Other experiments for that event retain their own status. Partial output cannot
be accepted by changing a label. Revisions or regenerated HTML need a review bound
to their actual bytes. Zero structural errors is not proof of semantic correctness.

## Withdraw a collection

In the search or graph panel, enter the confirmer and reason, then explicitly
withdraw the event's current collection. It removes `search/` or `epg/` from the
formal catalog and archives the exact files under ignored
`output/collections/<operation_id>/`. Graph withdrawal clears accepted paths and
sets the event to `in_review`; source runs and prior build inputs remain intact.
Recollection uses the same confirmation/review checks.

Lightweight receipts in `workbench/collections/<operation_id>.json` record the
action, identity, file hashes, time, confirmer and reason. Source bodies are not
included in receipts. Unknown files, symlinks, modified collected artifacts and
stale versions are protected. File and registry changes roll back on write errors.
No commit, push or destructive deletion of experiment records is automatic.
