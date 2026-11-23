// All navigation resolves against the embedded graph. Display aliases are local to this export.
const objects = new Map();
const register = (id, kind, record) => { if (id) objects.set(id, {kind, record}); };
for (const group of ['person', 'storyline', 'event']) register(graph[group]?.[group + '_id'], group, graph[group]);
for (const [group, kind] of [['stages', 'stage'], ['phases', 'phase'], ['actions', 'action'],
    ['contexts', 'context'], ['entities', 'entity'], ['sources', 'source'], ['evidence', 'evidence']]) {
  for (const row of graph[group] || []) register(row[kind + '_id'], kind, row);
}
const actionRelations = new Map(), sourcePassages = new Map();
for (const [i, row] of (graph.relations || []).entries()) {
  const id = row.relation_id || 'relation:' + (i + 1);
  register(id, 'relation', row);
  for (const endpoint of new Set([row.from_action_id, row.to_action_id])) {
    if (!actionRelations.has(endpoint)) actionRelations.set(endpoint, []);
    actionRelations.get(endpoint).push(id);
  }
}
for (const [id, ev] of evidence) {
  if (!sourcePassages.has(ev.source_id)) sourcePassages.set(ev.source_id, []);
  sourcePassages.get(ev.source_id).push(id);
}
const locationNotes = {handoff: 'Search handoff metadata or assembly text',
  ambiguous: 'Ambiguous quote location', unmatched: 'Quote not located', unverified: 'Frozen passage could not be verified'};
let selection = null, fieldFocus = null, backStack = [], returnTo = null;
const alias = id => view.aliases[id] || id;
const pretty = value => String(value || '').replaceAll('_', ' ');
const displayName = id => view.details[id]?.title || objects.get(id)?.record?.name || id;
const short = (value, n = 85) => value.length <= n ? value : value.slice(0, n - 1).trimEnd() + '…';
const contextCategories = new Map([
  ['environment', 'Environment'], ['relations', 'Parties & relationships'], ['person_state', 'Personal state']
]);
const contextPerspectives = new Map([
  ['world', 'World as described'], ['belief', 'Known or believed at the time'],
  ['post_hoc', 'Retrospective'], ['unknown', 'Unknown']
]);
const contextUses = new Map();
for (const [items, key, field] of [[graph.phases, 'phase_id', 'baseline_context_refs'],
    [graph.actions, 'action_id', 'delta_context_refs']]) {
  for (const item of items || []) for (const [i, ref] of (item[field] || []).entries()) {
    if (!contextUses.has(ref.context_id)) contextUses.set(ref.context_id, []);
    contextUses.get(ref.context_id).push({owner: item[key], path: '/' + field + '/' + i, ref});
  }
}
const scopeNames = {shared: 'Phase-wide', action: 'Action-linked', reference: 'Reference only'};
let contextScopes = new Map();
function contextScopesOn(page) {
  const actions = new Set(page.cards.filter(card => card.kind === 'action').map(card => card.id));
  const scopes = new Map();
  for (const card of page.cards) {
    if (card.kind !== 'context') continue;
    const uses = contextUses.get(card.id) || [];
    const coverage = card.baseline_coverage;
    const linked = uses.some(use => actions.has(use.owner));
    const kind = coverage ? 'shared' : linked ? 'action' : 'reference';
    scopes.set(card.id, {kind, coverage, label: coverage && linked ? 'Phase-wide and action-linked' : scopeNames[kind],
      members: coverage ? new Set(coverage.applies) : null});
  }
  return scopes;
}
function contextUseName(ref) {
  return [pretty(ref.relation_type), ref.relation_type === 'participation' && ref.role].filter(Boolean).join(' · ');
}
function at(record, path) {
  for (const part of (path || '').split('/').slice(1)) {
    record = record?.[part.replaceAll('~1', '/').replaceAll('~0', '~')];
  }
  return record;
}
const overlap = (a, b) => a === b || Boolean(a && b && (a.startsWith(b + '/') || b.startsWith(a + '/')));
function fieldName(path) {
  if (!path) return 'Whole record';
  const names = {from_action_id: 'From action', to_action_id: 'To action', entity_id: 'Entity',
    entity_refs: 'Entities mentioned', context_id: 'Referenced context', context_ref_id: 'Context reference',
    delta_context_refs: 'Action context', baseline_context_refs: 'Shared context',
    on_behalf_of: 'On behalf of', type: 'Type'};
  return path.split('/').slice(1).map(k => /^\d+$/.test(k) ? String(Number(k) + 1) :
    (names[k] || pretty(k).replace(/^./, c => c.toUpperCase()))).join(' › ');
}
function valueText(value) {
  if (value == null) return '';
  if (typeof value === 'string') return objects.has(value) ? displayName(value) : value;
  if (Array.isArray(value)) return value.map(valueText).join(' · ');
  if (typeof value === 'object') return Object.entries(value).filter(([k,v]) =>
    !['support','conflicts','gaps'].includes(k) && v != null).map(([k,v]) => pretty(k) + ' — ' + valueText(v)).join('\n');
  return String(value);
}
const symmetricRelation = type => ['overlaps', 'order_unknown', 'joint_action'].includes(type);
function relationName(r) {
  return [alias(r.from_action_id), pretty(r.type), alias(r.to_action_id)].join(' ');
}
function traceButton(text, id, field = null) {
  const button = el('button', text, 'trace-link');
  button.type = 'button';
  button.dataset.target = id;
  if (field !== null) button.dataset.field = field;
  button.onclick = () => inspectRecord(id, field);
  return button;
}
function passageButton(eid, withText = false) {
  const ev = evidence.get(eid);
  if (!ev) return el('span', 'Missing passage · ' + eid, 'field-note warning');
  const issue = view.passage_issues[eid];
  let name = alias(eid) + ' · ' + (issue ? locationNotes[issue] : alias(ev.source_id));
  if (withText && !issue) name += ' · ' + short(ev.quote, 90);
  return traceButton(name, eid);
}
function supportEntry(s) {
  const block = el('div', null, 'support');
  block.append(el('strong', {O: 'Source record', A: 'Source assertion', I: 'Inference'}[s.mode] || 'Recorded support'));
  if (s.reason) block.append(el('p', s.reason));
  for (const eid of s.evidence_ids || []) block.append(passageButton(eid));
  for (const p of s.premise_refs || []) {
    block.append(traceButton('Premise · ' + alias(p.object_id) + ' · ' + fieldName(p.field), p.object_id, p.field));
  }
  return block;
}
function fieldRows(parent, id, targets, focus = null, localPrefix = '') {
  const record = objects.get(id).record, index = view.fields[id] || {};
  for (const target of targets) {
    const row = el('details', null, 'claim');
    row.dataset.field = target;
    row.open = focus !== null && overlap(focus, target);
    const label = localPrefix && target.startsWith(localPrefix + '/') ? target.slice(localPrefix.length) : target;
    const summary = el('summary', fieldName(label));
    summary.onclick = () => {
      fieldFocus = row.open ? null : {id, field: target};
      paintEvidenceSelection();
    };
    row.append(summary);
    if (target) {
      const value = valueText(at(record, target));
      if (value) row.append(el('p', value));
    }
    const refs = index[target] || {};
    for (const path of refs.support || []) row.append(supportEntry(at(record, path)));
    for (const path of refs.gaps || []) row.append(el('p', 'Gap · ' + at(record, path).reason, 'field-note warning'));
    for (const path of refs.conflicts || []) {
      const c = at(record, path);
      row.append(el('p', 'Conflict · ' + c.reason, 'field-note warning'));
      for (const alternative of c.alternatives || []) {
        row.append(el('p', 'Alternative · ' + valueText(alternative.value)));
        for (const s of alternative.support || []) row.append(supportEntry(s));
      }
    }
    if (!refs.support?.length && !refs.gaps?.length && !refs.conflicts?.length)
      row.append(el('p', 'No separate support recorded for this field.', 'field-note'));
    parent.append(row);
  }
}
function partyEntries(parent, id) {
  const entries = view.party_uses[id] || [];
  if (!entries.length) return;
  parent.append(el('h3', 'Roles and mentions in this event'));
  for (const use of entries) {
    const owner = objects.get(use.owner).record, value = at(owner, use.path);
    const part = el('details', null, 'occurrence');
    part.dataset.owner = use.owner;
    part.dataset.path = use.path;
    const summary = el('summary', use.label + ' · ' + alias(use.owner) + ' · ' + short(displayName(use.owner)));
    summary.onclick = () => {
      fieldFocus = part.open ? null : {id: use.owner, field: use.path};
      paintEvidenceSelection();
    };
    part.append(summary);
    const targets = new Set(use.fields);
    if (use.label === 'Participation' && use.fields.length === 1 && use.fields[0] === use.path + '/context_id') {
      part.append(el('p', 'The cited passages apply to the context reference. Identity and role have no separate citation here.', 'field-note'));
    }
    if (value && typeof value === 'object') {
      for (const key of ['entity_id', 'capacity', 'role', 'on_behalf_of', 'qualification']) {
        if (value[key] == null) continue;
        const path = use.path + '/' + key;
        part.append(el('p', fieldName('/' + key) + ' · ' + valueText(value[key])));
        if (!use.fields.some(p => overlap(p, path))) targets.add(path);
      }
    }
    if (!targets.size) targets.add(use.path);
    fieldRows(part, use.owner, targets, null, use.path);
    part.append(traceButton('Open ' + alias(use.owner), use.owner, use.path));
    parent.append(part);
  }
}
function fieldsFor(id, field) {
  const fields = Object.keys(view.fields[id] || {});
  return field === null ? fields : fields.filter(p => overlap(p, field));
}
function selectedPassages(id, field) {
  if (evidence.has(id)) return new Set([id]);
  if (sources.has(id)) return new Set(sourcePassages.get(id) || []);
  const found = new Set(), record = objects.get(id)?.record;
  for (const key of fieldsFor(id, field)) {
    for (const p of view.fields[id][key].support || [])
      for (const eid of at(record, p).evidence_ids || []) found.add(eid);
  }
  return found;
}
function renderInspection() {
  const {id, field} = selection, {kind, record} = objects.get(id);
  const panel = $('inspection');
  panel.replaceChildren(el('div', pretty(kind).toUpperCase() + ' · ' + alias(id), 'inspection-meta'));
  const title = el('h2', kind === 'relation' ? relationName(record) :
    kind === 'evidence' ? (view.passage_issues[id] ? 'Recorded reference' : 'Quoted passage') : displayName(id));
  title.id = 'inspection-title'; title.tabIndex = -1;
  panel.append(title);
  if (kind === 'evidence') {
    const issue = view.passage_issues[id];
    if (issue) panel.append(el('p', locationNotes[issue], 'field-note warning'));
    panel.append(el(issue ? 'p' : 'blockquote', record.quote));
    if (!issue && !view.checked_input)
      panel.append(el('p', 'Location from the saved graph. A frozen build input was not supplied.', 'field-note'));
    if (record.sample_id) {
      const span = Number.isInteger(record.start) && Number.isInteger(record.end) ?
        ' · [' + record.start + ', ' + record.end + ')' : '';
      panel.append(el('p', record.sample_id + span, 'inspection-meta'));
    }
    if (record.locator) panel.append(el('p', valueText(record.locator), 'inspection-meta'));
    if (sources.has(record.source_id)) {
      panel.append(el('h3', 'Source'), traceButton(alias(record.source_id) + ' · ' + displayName(record.source_id), record.source_id));
    }
  } else if (kind === 'source') {
    for (const [label, value] of [['Published', record.published_at], ['Retrieved', record.retrieved_at], ['Origin', record.origin]])
      if (value) panel.append(el('p', label + ' · ' + value, 'inspection-meta'));
    if (/^https?:\/\//i.test(record.url || '')) {
      const link = el('a', 'Open original source ↗');
      link.href = record.url; link.target = '_blank'; link.rel = 'noopener noreferrer'; panel.append(link);
    }
    const ids = sourcePassages.get(id) || [];
    for (const [label, items] of [['Passages in this event', ids.filter(e => !view.passage_issues[e])],
                                  ['References to review', ids.filter(e => view.passage_issues[e])]]) {
      if (!items.length) continue;
      panel.append(el('h3', label + ' (' + items.length + ')'));
      const list = el('div', null, 'passage-list');
      items.forEach(e => list.append(passageButton(e, true))); panel.append(list);
    }
    if (!ids.length) panel.append(el('p', 'No passages recorded for this source.', 'field-note'));
  } else {
    for (const key of ['description', 'summary']) if (record[key] && record[key] !== title.textContent) panel.append(el('p', record[key]));
    if (record.time?.text) panel.append(el('p', record.time.text, 'inspection-meta'));
    if (/^\/(?:baseline|delta)_context_refs\/\d+$/.test(field || '')) {
      const ref = at(record, field);
      if (ref) {
        panel.append(el('h3', 'Context reference'), traceButton(alias(ref.context_id) + ' · ' + contextUseName(ref), ref.context_id));
        if (ref.entity_id) panel.append(traceButton(displayName(ref.entity_id), ref.entity_id));
        else if (['knowledge-source', 'participation'].includes(ref.relation_type))
          panel.append(el('p', ref.relation_type === 'knowledge-source' ? 'Recipient not recorded' : 'Participant not recorded', 'field-note'));
        if (ref.interaction_type) panel.append(el('p', pretty(ref.interaction_type)));
        if (ref.qualification) panel.append(el('p', ref.qualification));
        if (kind === 'phase') {
          const branches = view.pages.find(page => page.phase === id)?.edges.filter(edge =>
            edge.inherited && edge.ref_path === field) || [];
          if (branches.length) {
            const row = el('div', null, 'relation-list');
            row.append(el('span', 'Applies by default to'));
            for (const branch of branches) row.append(traceButton(alias(branch.to), branch.to));
            panel.append(row);
            for (const branch of branches) for (const path of branch.direct_paths || []) {
              panel.append(traceButton('Explicit reference on ' + alias(branch.to), branch.to, path));
            }
          }
        }
      }
    }
    if (kind === 'context') {
      const scope = contextScopes.get(id);
      if (scope) panel.append(el('p', 'Scope on this page · ' + scope.label, 'inspection-meta'));
      const coverage = scope?.coverage;
      if (coverage) {
        const {applies, excluded, unresolved} = coverage, total = applies.length + excluded.length + unresolved.length;
        const summary = total ? 'Applies by default to ' + applies.length + ' of ' + total +
          (total === 1 ? ' Action in ' : ' Actions in ') + phaseLabel(view.pages[current]) + '.' :
          'No Actions are recorded in this phase.';
        panel.append(el('p', summary, 'field-note scope-summary'));
        for (const [label, ids] of [['Highlighted', applies], ['Excluded', excluded], ['Scope unresolved', unresolved]]) {
          if (ids.length) panel.append(el('p', label + ' · ' + ids.map(alias).join(', '), 'inspection-meta'));
        }
        const mentioned = (record.entity_refs || []).filter(eid => objects.has(eid));
        if (mentioned.length) {
          panel.append(el('h3', 'Entities mentioned'));
          for (const eid of mentioned) panel.append(traceButton(displayName(eid), eid));
        }
      }
      panel.append(el('p', 'Category · ' + (contextCategories.get(record.category) || 'Not recorded'), 'inspection-meta'),
        el('p', 'Perspective · ' + (contextPerspectives.get(record.perspective) || 'Not recorded'), 'inspection-meta'));
      const uses = contextUses.get(id) || [];
      if (uses.length) {
        panel.append(el('h3', 'Recorded uses'));
        for (const {owner, path, ref} of uses) {
          const party = ref.entity_id && displayName(ref.entity_id);
          panel.append(traceButton([alias(owner), contextUseName(ref), party].filter(Boolean).join(' · '), owner, path));
        }
      }
    }
    if (kind === 'action') {
      const chronology = view.pages.flatMap(p => p.cards).find(c => c.id === id)?.chronology;
      if (chronology) {
        panel.append(el('h3', 'Chronology in this phase'));
        if (record.time?.text) panel.append(el('p', record.time.text, 'inspection-meta'));
        if (chronology.note) panel.append(el('p', chronology.note, 'inspection-meta'));
        const cell = chronology.placement;
        if (cell?.note && cell.note !== chronology.note) panel.append(el('p', cell.note, 'field-note'));
        if (cell?.mark === 'scope') {
          panel.append(el('p', 'This guide shows Phase membership. The Action has no supported calendar position here.', 'inspection-meta'));
        } else if (cell?.mark) {
          const label = timeMarkName(cell.mark);
          const time = record.time || {};
          panel.append(el('p', [label, time.start, time.end && 'until ' + time.end + ' (exclusive)']
            .filter(Boolean).join(' · '), 'inspection-meta'));
          if (cell.mark === 'upper' || cell.mark === 'lower') {
            panel.append(el('p', cell.mark === 'upper'
              ? 'The Action could occur before or during the indicated period.'
              : 'The Action could occur during or after the indicated period.', 'inspection-meta'));
          }
        }
        for (const [key, label] of [['earlier', 'Earlier'], ['later', 'Later'], ['unordered', 'Order unresolved'],
          ['anchor_before', 'Dated predecessors'], ['anchor_after', 'Dated successors']]) {
          const ids = chronology[key] || [];
          if (!ids.length) continue;
          const row = el('div', null, 'relation-list');
          row.append(el('span', label));
          for (const aid of ids) {
            const basis = ['earlier', 'later'].includes(key)
              ? (chronology.by_time.includes(aid) ? ' · dated windows' : ' · order path') : '';
            row.append(traceButton(alias(aid) + basis, aid));
          }
          panel.append(row);
        }
        if (chronology.order_steps?.length) {
          const row = el('div', null, 'relation-list');
          row.append(el('span', 'Recorded precedence steps'));
          for (const rid of chronology.order_steps) row.append(traceButton(relationName(objects.get(rid).record), rid));
          panel.append(row);
        }
      }
    }
    if (kind === 'action' && record.baseline_context_exclusions?.length) {
      panel.append(el('h3', 'Recorded exceptions to shared context'));
      const baseline = objects.get(record.phase_id)?.record.baseline_context_refs || [];
      for (const [i, exclusion] of record.baseline_context_exclusions.entries()) {
        const ref = baseline.find(r => r.context_ref_id === exclusion.context_ref_id);
        const label = ref ? alias(ref.context_id) + ' · ' + contextUseName(ref) : exclusion.context_ref_id;
        panel.append(traceButton([label, exclusion.reason].filter(Boolean).join(' · '),
          id, '/baseline_context_exclusions/' + i));
      }
    }
    if (kind === 'entity' || kind === 'person') {
      if (record.aliases?.length) panel.append(el('p', 'Aliases · ' + record.aliases.join(', '), 'inspection-meta'));
      partyEntries(panel, id);
    }
    if (kind === 'relation') {
      const link = selectedPhaseLink();
      if (link) {
        const go = el('button', 'Go to ' + alias(link.id) + ' · ' + phaseLabel(view.pages[link.page]), 'trace-link');
        go.onclick = () => followPhaseLink(link);
        panel.append(go);
      }
      panel.append(el('p', 'Recorded basis · ' + pretty(record.basis || 'unspecified'), 'inspection-meta'));
      for (const [label, endpoint] of [['From', record.from_action_id], ['To', record.to_action_id]])
        panel.append(traceButton(label + ' · ' + alias(endpoint) + ' · ' + short(displayName(endpoint)), endpoint));
    }
    const targets = new Set(Object.keys(view.fields[id] || {}));
    if (kind === 'relation') {
      for (const path of ['/from_action_id', '/to_action_id', '/type']) targets.add(path);
    }
    if (field !== null && !fieldsFor(id, field).length) targets.add(field);
    if (targets.size) {
      panel.append(el('h3', 'Evidence by field'));
      fieldRows(panel, id, targets, field);
    }
    const links = actionRelations.get(id) || [];
    if (links.length) {
      panel.append(el('h3', 'Action relations'));
      const list = el('div', null, 'relation-list');
      for (const rid of links) list.append(traceButton(relationName(objects.get(rid).record), rid));
      panel.append(list);
    }
  }
  $('inspection-back').disabled = !backStack.length;
  panel.scrollTop = 0;
  title.focus({preventScroll: true});
  if (field !== null) panel.querySelector('.claim[open]')?.scrollIntoView({block: 'nearest'});
}
function inspectRecord(id, field = null, remember = true) {
  if (!objects.has(id)) return;
  if (!selection) returnTo = document.activeElement;
  if (selection && remember) backStack.push({...selection, fieldFocus, scroll: $('inspection').scrollTop,
    open: [...$('inspection').querySelectorAll('details')].map(d => d.open)});
  selection = {id, field}; fieldFocus = null;
  expanded = [...cards].find(([, item]) => item.card.id === id)?.[0] || null;
  for (const [key, item] of cards) item.button.setAttribute('aria-expanded', String(key === expanded));
  $('inspector').hidden = false;
  renderInspection();
  markPhaseDestination();
  highlight(null);
  paintEvidenceSelection();
}
function closeInspection(restore = true) {
  if (!selection) return;
  selection = null; fieldFocus = null; expanded = null; backStack = [];
  $('inspector').hidden = true;
  markPhaseDestination();
  for (const item of cards.values()) item.button.setAttribute('aria-expanded', 'false');
  if (restore && returnTo?.isConnected) returnTo.focus({preventScroll: true});
  returnTo = null;
  highlight(null);
  paintEvidenceSelection();
}
$('inspection-close').onclick = () => closeInspection();
$('inspection-back').onclick = () => {
  const last = backStack.pop();
  if (!last) return;
  inspectRecord(last.id, last.field, false);
  [...$('inspection').querySelectorAll('details')].forEach((d, i) => { d.open = last.open[i]; });
  $('inspection').scrollTop = last.scroll;
  fieldFocus = last.fieldFocus;
  paintEvidenceSelection();
};
document.addEventListener('keydown', e => {
  if (e.key === 'Escape' && selection) { e.preventDefault(); closeInspection(); }
});
