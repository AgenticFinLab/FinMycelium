'use strict';
const epg = JSON.parse(document.getElementById('epg-data').textContent);
const DAY = 86400000,
  focal = epg.graph.subject_entity_id;
const index = (table, key) => new Map(epg[table].map(row => [row[key], row]));
const entities = index('entity', 'entity_id'),
  activities = index('activity', 'activity_id');
const actions = index('action', 'action_id'),
  transactions = index('financial_transaction', 'transaction_id');
const occurrences = index('occurrence', 'occurrence_id'),
  times = index('time_value', 'time_id');
const evidenceSets = index('evidence_set', 'evidence_set_id');
const esc = value => String(value ?? '').replace(/[&<>"']/g, c => ({
  '&': '&amp;',
  '<': '&lt;',
  '>': '&gt;',
  '"': '&quot;',
  "'": '&#39;'
} [c]));
const wrap = (value, width = 68) => {
  let line = '',
    lines = [];
  for (const word of String(value ?? '').split(/\s+/)) {
    if (line && line.length + word.length > width) {
      lines.push(line);
      line = word;
    } else line += (line ? ' ' : '') + word;
  }
  if (line) lines.push(line);
  return lines.map(esc).join('<br>');
};
const ordered = rows => rows.slice().sort((a, b) => a.sort_order - b.sort_order);
const label = id => entities.get(id)?.name || 'Unknown';
// Stable colors follow stored entity order; the focal person is always blue.
const palette = [{
  color: '#1f77b4',
  symbol: 'circle'
}, {
  color: '#aec7e8',
  symbol: 'circle'
}, {
  color: '#2694e1',
  symbol: 'square'
}, {
  color: '#8295ae',
  symbol: 'diamond'
}, {
  color: '#8295ae',
  symbol: 'diamond'
}, {
  color: '#c8e4ff',
  symbol: 'cross'
}, {
  color: '#d9f8ff',
  symbol: 'square'
}, {
  color: '#93a9c5',
  symbol: 'circle'
}];
const entityStyles = new Map(ordered(epg.entity).map((row, i) => [row.entity_id, palette[i % palette
  .length]]));
entityStyles.set(focal, palette[0]);
const style = id => entityStyles.get(id) || palette[palette.length - 1];
const relationLabel = type => type === 'CEO and Chairman' ? 'Chairman and CEO' : type;
const relationTypes = [...new Set(epg.entity_relation.map(r => relationLabel(r.relation_type)))];
const relationStyles = {
  'CEO': {
    color: '#984ea3',
    dash: 'dot'
  },
  'Chairman and CEO': {
    color: '#e41a1c',
    dash: 'solid'
  },
  'Chief Executive Officer': {
    color: '#ff7f00',
    dash: 'solid'
  },
  'Colleague and partner at Berkshire Hathaway': {
    color: '#4daf4a',
    dash: 'dashdot'
  },
  'Investor': {
    color: '#b4ae2a',
    dash: 'dash'
  },
  'Vice Chairman': {
    color: '#377eb8',
    dash: 'dash'
  }
};
const relationStyle = type => ({
  width: 1.25,
  ...(relationStyles[relationLabel(type)] || {
    color: '#84989f',
    dash: 'solid'
  })
});

function parseTime(value) {
  if (!value) return null;
  if (/^\d{4}-\d{2}-\d{2}T/.test(value)) {
    const instant = Date.parse(value);
    return Number.isFinite(instant) ? {lo:instant, hi:instant, raw:value, approx:false} : null;
  }
  const match = String(value).match(/^(\d{4})(?:-(\d{2}))?(?:-(\d{2}))?$/);
  if (!match) return null;
  const year = Number(match[1]),
    month = Number(match[2] || 1),
    day = Number(match[3] || 1);
  const lo = Date.parse(
    `${match[1]}-${String(month).padStart(2,'0')}-${String(day).padStart(2,'0')}T00:00:00Z`);
  if (!Number.isFinite(lo) || new Date(lo).getUTCMonth() !== month - 1) return null;
  const next = new Date(lo);
  if (!match[2]) next.setUTCFullYear(year + 1);
  else if (!match[3]) next.setUTCMonth(month);
  return {
    lo,
    hi: match[3] ? lo : next.getTime() - DAY,
    raw: value,
    original: value,
    approx: !match[3]
  };
}

function timeRange(id) {
  const t = times.get(id);
  if (!t) return null;
  if (t.window_start && t.window_end) return {
    lo: Date.parse(t.window_start),
    hi: Date.parse(t.window_end),
    approx: !!t.is_approximate || t.window_semantics === 'uncertainty',
    raw: t.value,
    original: t.original_text,
    semantics: t.window_semantics
  };
  return parseTime(t.value);
}
const knownTimes = epg.time_value.map(t => timeRange(t.time_id)).filter(Boolean);
const coverageStart = parseTime(epg.graph.coverage_start),
  coverageEnd = parseTime(epg.graph.coverage_end);
const hasDates = !!(coverageStart || coverageEnd || knownTimes.length);
const first = coverageStart?.lo ?? (knownTimes.length ? Math.min(...knownTimes.map(t => t.lo)) : 0);
const last = Math.max(first, coverageEnd?.hi ?? (knownTimes.length ? Math.max(...knownTimes.map(t =>
  t.hi)) : first));

function timeText(t) {
  if (!t) return 'Undated';
  const original = t.original ? `<br>Original expression: ${esc(t.original)}` : '';
  if (t.approx)
  return `${esc(t.raw==='unknown'?'Date not specified':t.raw)}${original}<br>Recorded range: ${new Date(t.lo).toISOString().slice(0,10)} – ${new Date(t.hi).toISOString().slice(0,10)}${t.semantics==='duration'?'<br>Approximate duration':'<br>Approximate placement; the range does not assert continuous activity.'}`;
  return esc(t.raw);
}

function fact(member) {
  const a = activities.get(member.activity_id);
  let row, kind, title, actor, oid, time;
  if (a.action_id) {
    row = actions.get(a.action_id);
    kind = 'action';
    title = row.action_type;
    actor = row.actor_id;
    oid = row.occurrence_id;
    time = timeRange(row.timestamp_time_id);
  } else if (a.transaction_id) {
    row = transactions.get(a.transaction_id);
    kind = 'transaction';
    title = row.name;
    actor = null;
    oid = row.occurrence_id;
    time = timeRange(row.timestamp_time_id);
  } else {
    row = occurrences.get(a.context_occurrence_id);
    kind = 'context';
    title = row.title;
    actor = null;
    oid = row.occurrence_id;
    time = timeRange(row.start_time_id);
    const end = timeRange(row.end_time_id);
    if (time && end) time = {
      ...time,
      hi: end.hi
    };
  }
  const selections = new Set(epg.event_activity_detail.filter(d => d.event_id === member.event_id &&
    d.activity_id === member.activity_id).map(d => d.detail_index));
  const details = epg.activity_detail.filter(d => d.activity_id === member.activity_id && (member
    .detail_mode === 'all' || selections.has(d.detail_index))).sort((a, b) => a.detail_index - b
    .detail_index);
  const metadata = evidenceSets.get(row.evidence_set_id)?.field_metadata || {};
  const plotTime = time && (time.hi < first || time.lo > last) ? null : time;
  return {
    member,
    row,
    kind,
    title: member.display_title || title,
    actor,
    oid,
    time,
    plotTime,
    details,
    metadata
  };
}

// Enrichment appends canonical rows so earlier facts and their stored order stay
// intact. Only these added rows may move in the display, and only when their
// recorded time range is wholly before a later row. Unknown/overlapping dates
// do not justify inventing an order. No package row is modified here.
function insertEnrichmentByTime(rows, isAdded, rangeFor) {
  const stored = ordered(rows),
    result = stored.filter(row => !isAdded(row)),
    undated = [];
  for (const row of stored.filter(isAdded)) {
    const range = rangeFor(row);
    if (!range || !Number.isFinite(range.lo) || !Number.isFinite(range.hi)) {
      undated.push(row);
      continue;
    }
    const before = result.findIndex(other => {
      const next = rangeFor(other);
      return next && Number.isFinite(next.lo) && range.hi < next.lo;
    });
    if (before < 0) result.push(row);
    else result.splice(before, 0, row);
  }
  return result.concat(undated);
}

const addedMember = member => member.activity_id.startsWith('EF_ACTIVITY_');
const displayMembers = members => insertEnrichmentByTime(members, addedMember,
  member => fact(member).time);

function displayBlocks(members, stages) {
  const blocks = [...stages.map(stage => ({sort_order: stage.sort_order, stage})),
    ...members.filter(member => !member.stage_id).map(member => ({
      sort_order: member.sort_order, member
    }))];
  const rangeFor = block => {
    if (block.member) return fact(block.member).time;
    const ranges = members.filter(member => member.stage_id === block.stage.stage_id)
      .map(member => fact(member).time)
      .filter(range => range && Number.isFinite(range.lo) && Number.isFinite(range.hi));
    // The earliest documented activity locates a stage; it does not assert an
    // undocumented stage boundary or reassign existing activities.
    return ranges.sort((a, b) => a.lo - b.lo || a.hi - b.hi)[0] || null;
  };
  return insertEnrichmentByTime(blocks,
    block => block.stage ? block.stage.stage_id.startsWith('EF_STAGE_') : addedMember(block.member),
    rangeFor);
}

function activityTitle(id) {
  const m = epg.event_activity.find(m => m.activity_id === id && m.display_title);
  if (m) return m.display_title;
  const a = activities.get(id);
  return a?.action_id ? actions.get(a.action_id)?.action_type : a?.transaction_id ? transactions
    .get(a.transaction_id)?.name : occurrences.get(a?.context_occurrence_id)?.title;
}

function linkHover(r) {
  return `<h3>${esc(r.description||r.relation_type)}</h3><p>${esc(activityTitle(r.from_activity_id))} → ${esc(activityTitle(r.to_activity_id))}</p>`;
}

function relationTime(r) {
  const show = id => {
    const t = times.get(id);
    return t?.original_text || (t?.value && t.value !== 'unknown' ? t.value : '未记载');
  };
  return show(r.valid_from_time_id) + ' — ' + show(r.valid_to_time_id);
}

function factHover(f, event, stage) {
  const oc = occurrences.get(f.oid), m = f.metadata;
  const isPDF = m.provenance === 'supplied_pdf';
  const relatedIds = new Set(epg.relation_occurrence
    .filter(r => r.occurrence_id === f.oid).map(r => r.relation_id));
  const relations = epg.entity_relation.filter(r => relatedIds.has(r.relation_id));
  const links = epg.activity_relation.filter(r =>
    r.from_activity_id === f.member.activity_id || r.to_activity_id === f.member.activity_id);
  const participants = epg.occurrence_participant
    .filter(p => p.occurrence_id === f.oid).map(p => label(p.entity_id));

  let who = `Context: ${esc(participants.join(' / '))}`;
  if (f.kind === 'action') who = `Actor: ${esc(label(f.actor))}`;
  if (f.kind === 'transaction') {
    who = `Transaction parties: ${esc(label(f.row.from_entity_id))} → ${esc(label(f.row.to_entity_id))}`;
  }
  let dates = timeText(f.time);
  if (isPDF) {
    who = `主体：${esc(m.actor)}`;
    dates = `发生时间：${esc(m.original_time)}`;
    if (f.time?.approx) {
      dates += `<br>定位范围：${new Date(f.time.lo).toISOString().slice(0,10)} — ${new Date(f.time.hi).toISOString().slice(0,10)}（约）`;
    }
    if (m.reported_at) dates += '<br>报道／回述日期：' + esc(m.reported_at);
    if (m.placement_note) dates += '<br>' + esc(m.placement_note);
  }
  const parts = [
    `<div>${esc(event.label)}${stage ? ' / ' + esc(stage.label) : ''}</div>`,
    `<h3>${esc(f.title)}</h3><p>${who}<br>${dates}</p>`,
    ...f.details.map(d => `<p>${esc(d.value)}</p>`)
  ];
  if (f.kind === 'transaction') {
    parts.push(...(f.row.details || []).map(d => `<p>${esc(d)}</p>`));
  }
  parts.push(`<details><summary>${isPDF ? '发生场景' : 'Occurrence & context'}</summary>`,
    `<p>${esc(oc.title)}</p>`);
  if (!isPDF) {
    parts.push(...(oc.descriptions || []).map(d => `<p>${esc(d)}</p>`),
      `<p>${esc(oc.subject_relevance)}</p>`);
  }
  parts.push('</details>');
  if (links.length) {
    parts.push(`<details><summary>行为联系 (${links.length})</summary>`);
    for (const r of links) {
      parts.push(`<p><b>${esc(r.description || r.relation_type)}</b><br>` +
        `${esc(activityTitle(r.from_activity_id))} → ${esc(activityTitle(r.to_activity_id))}</p>`);
    }
    parts.push('</details>');
  }
  if (relations.length) {
    parts.push(`<details><summary>Relationships (${relations.length})</summary>`);
    for (const r of relations) {
      parts.push(`<p>${esc(label(r.from_entity_id))} → ${esc(label(r.to_entity_id))}<br>` +
        `<b>${esc(r.relation_type)}</b><br>有效时间：${esc(relationTime(r))}</p>`);
    }
    parts.push('</details>');
  }
  return parts.join('');
}

const gd = document.getElementById('gantt');
const openEvents = new Set(ordered(epg.event).slice(0, 1).map(e => e.event_id)),
  closedDomains = new Set();
let xRange = [new Date(first - 12 * DAY).toISOString(), new Date(last + 12 * DAY).toISOString()];
let annotationMap = {},
  cards = [],
  queue = Promise.resolve();

// Plotly SVG hover labels need explicit line breaks. Preserve all non-evidence
// content and inline formatting; wrapping must never truncate the text.
function nativeHover(html) {
  const text = html.replace(/<h[34]>(.*?)<\/h[34]>/g, '<b>$1</b><br>')
    .replace(/<summary>(.*?)<\/summary>/g, '<br><b>$1</b><br>')
    .replace(/<\/(?:p|blockquote|div)>/g, '<br>')
    .replace(/<(?:p|blockquote|div|span|details)[^>]*>|<\/(?:span|details)>/g, '')
    .replace(/(?:<br>){3,}/g, '<br><br>');
  const lines = [], width = 68;
  const columnsFor = token => token.startsWith('<') ? 0 : token.codePointAt(0) > 0xff ? 2 : 1;
  for (const paragraph of text.split(/<br\s*\/?>/)) {
    // Treat escaped entities as one character; also wrap CJK and long URLs.
    const tokens = paragraph.replace(/\s+/g, ' ').match(/<[^>]*>|&(?:#\d+|#x[\da-f]+|[a-z]+);|[\s\S]/giu) || [];
    let line = [], columns = 0;
    for (const token of tokens) {
      const size = columnsFor(token);
      if (columns + size > width) {
        const space = line.lastIndexOf(' ');
        const cut = space >= line.length / 2 ? space + 1 : line.length;
        lines.push(line.slice(0, cut).join(''));
        line = line.slice(cut);
        columns = line.reduce((n, c) => n + columnsFor(c), 0);
      }
      line.push(token);
      columns += size;
    }
    lines.push(line.join(''));
  }
  return lines.join('<br>');
}
const actor = f => f.actor || f.row.from_entity_id || epg.occurrence_participant.find(p => p
  .occurrence_id === f.oid)?.entity_id;
const date = f => f.plotTime ? new Date((f.plotTime.lo + f.plotTime.hi) / 2).toISOString() : 0;
const info = (html, control) => ({
  html,
  control
});

function push(data, trace, detail) {
  cards[data.length] = detail;
  data.push({
    ...trace,
    hovertext: trace.y.map(() => nativeHover(detail.html)),
    hovertemplate: '%{hovertext}<extra></extra>',
    showlegend: false
  });
}

function labelAt(a, text, y, level, control) {
  annotationMap[a.length] = control;
  a.push({
    xref: 'paper',
    x: 0,
    xanchor: 'left',
    xshift: -324 + level * 18,
    y,
    yanchor: 'middle',
    text,
    align: 'left',
    showarrow: false,
    font: {
      size: level ? 15 : 16,
      color: level ? '#222222' : '#2a3f5f'
    },
    captureevents: true
  });
}

function summary(data, shapes, members, y, html, control, green = false) {
  const fs = members.map(fact),
    known = fs.filter(f => f.plotTime),
    unknown = fs.some(f => !f.plotTime);
  const marker = {
    color: 'rgba(173,216,230,.04)',
    line: {
      color: green ? '#a4b589' : '#9eafb8',
      width: 1
    },
    pattern: {
      shape: '/',
      fillmode: 'replace',
      bgcolor: 'rgba(173,216,230,.04)',
      fgcolor: green ? 'rgba(130,146,104,.25)' : 'rgba(125,155,169,.35)',
      size: 8,
      solidity: .12
    }
  };
  if (known.length) {
    const lo = Math.min(...known.map(f => f.plotTime.lo)),
      hi = Math.max(...known.map(f => f.plotTime.hi));
    push(data, {
      type: 'bar',
      orientation: 'h',
      base: [new Date(lo - 10 * DAY).toISOString()],
      x: [hi - lo + 20 * DAY],
      y: [y],
      width: 30,
      marker
    }, info(html, control));
  }
  if (unknown) push(data, {
    type: 'bar',
    orientation: 'h',
    base: [-.65],
    x: [1.3],
    y: [y],
    xaxis: 'x2',
    width: 30,
    marker
  }, info(html, control));
  const seen = new Set();
  for (const f of fs) {
    const k = JSON.stringify(f.plotTime);
    if (seen.has(k)) continue;
    seen.add(k);
    push(data, {
      type: 'scatter',
      mode: 'markers',
      x: [date(f)],
      y: [y],
      ...(f.plotTime ? {} : {
        xaxis: 'x2'
      }),
      marker: {
        color: '#ADD8E6',
        line: {
          color: 'black',
          width: 1
        },
        size: 12,
        symbol: 'diamond'
      }
    }, info(html, control));
  }
}

function activityRow(data, shapes, f, event, stage, y) {
  const t = f.plotTime,
    entity = actor(f),
    s = style(entity),
    html = factHover(f, event, stage),
    x = date(f),
    axis = t ? 'x' : 'x2';
  if (t && t.lo !== t.hi) shapes.push({
    type: 'rect',
    xref: axis,
    yref: 'y',
    x0: new Date(t.lo).toISOString(),
    x1: new Date(t.hi).toISOString(),
    y0: y - 12,
    y1: y + 12,
    fillcolor: t.approx ? 'rgba(0,0,0,0)' : 'rgba(230,245,201,.6)',
    line: {
      color: '#829268',
      width: 1.3,
      dash: t.approx ? 'dash' : 'solid'
    },
    layer: 'below'
  });
  else if (t) shapes.push({
    type: 'circle',
    xref: axis,
    yref: 'y',
    x0: new Date(t.lo - 8 * DAY).toISOString(),
    x1: new Date(t.lo + 8 * DAY).toISOString(),
    y0: y - 13,
    y1: y + 13,
    fillcolor: 'rgba(230,245,201,.25)',
    line: {
      color: '#c7dbac',
      dash: 'dash',
      width: 1
    },
    layer: 'below'
  });
  push(data, {
    type: 'scatter',
    mode: 'markers',
    meta: {
      kind: 'activity',
      event_id: event.event_id,
      stage_id: stage?.stage_id || null,
      activity_id: f.member.activity_id
    },
    x: [x],
    y: [y],
    xaxis: axis,
    marker: {
      color: s.color,
      symbol: s.symbol,
      size: entity === focal ? 11 : 8,
      line: {
        color: 'black',
        width: 1
      }
    }
  }, info(html));
  // A transparent wide target makes short/approximate ranges easy to inspect.
  if (t && t.lo !== t.hi) push(data, {
    type: 'scatter',
    mode: 'lines',
    x: [new Date(t.lo).toISOString(), new Date(t.hi).toISOString()],
    y: [y, y],
    line: {
      color: 'rgba(0,0,0,0)',
      width: 24
    }
  }, info(html));
  const related = new Set(epg.relation_occurrence.filter(r => r.occurrence_id === f.oid).map(r => r
    .relation_id));
  const relations = epg.entity_relation.filter(r => related.has(r.relation_id) && (r
    .from_entity_id === entity || r.to_entity_id === entity));
  const used = new Set();
  let n = 0;
  for (const r of relations) {
    const other = r.from_entity_id === entity ? r.to_entity_id : r.from_entity_id;
    if (used.has(other)) continue;
    used.add(other);
    n++;
    const rs = relationStyle(r.relation_type),
      os = style(other),
      xx = t ? new Date(Date.parse(x) + n * 13 * DAY).toISOString() : n * .3;
    push(data, {
      type: 'scatter',
      mode: 'lines',
      x: [x, xx],
      y: [y, y - 5],
      xaxis: axis,
      line: rs
    }, info(
      `<h3>${esc(r.relation_type)}</h3><p>${esc(label(r.from_entity_id))} → ${esc(label(r.to_entity_id))}</p><p>有效时间：${esc(relationTime(r))}</p>`
      ));
    push(data, {
      type: 'scatter',
      mode: 'markers',
      x: [xx],
      y: [y - 5],
      xaxis: axis,
      marker: {
        color: os.color,
        symbol: os.symbol,
        size: 6,
        line: {
          color: 'black',
          width: .6
        }
      }
    }, info(
      `<h3>${esc(label(other))}</h3><p>${esc(r.relation_type)}</p>`
      ));
  }
}

function build() {
  const data = [],
    shapes = [],
    annotations = [];
  cards = [];
  annotationMap = {};
  let y = 20;
  for (const domain of ordered(epg.domain)) {
    labelAt(annotations,
      `<b>${closedDomains.has(domain.domain_id)?'▸':'▾'} ${wrap(domain.label.toUpperCase(),28)}</b>`,
      y, 0, {
        type: 'domain',
        id: domain.domain_id
      });
    shapes.push({
      type: 'line',
      xref: 'paper',
      x0: 0,
      x1: 1,
      y0: y + 23,
      y1: y + 23,
      line: {
        color: '#d8e0e8',
        width: 1
      },
      layer: 'below'
    });
    y += 58;
    if (closedDomains.has(domain.domain_id)) continue;
    for (const event of ordered(epg.event.filter(e => e.domain_id === domain.domain_id))) {
      const members = ordered(epg.event_activity.filter(m => m.event_id === event.event_id)),
        stages = ordered(epg.stage.filter(s => s.event_id === event.event_id)),
        ctl = {
          type: 'event',
          id: event.event_id
        },
        opened = openEvents.has(event.event_id);
      labelAt(annotations, `<b>${opened?'▾':'▸'} ${wrap(event.label,31)}</b>`, y, 1, ctl);
      summary(data, shapes, members, y,
        `<h3>${esc(event.label)}</h3><p>${esc(event.summary)}</p><p>${members.length} activities</p>`,
        ctl);
      y += 66;
      if (!opened) continue;
      const positions = new Map();
      const blocks = displayBlocks(members, stages);
      for (const b of blocks) {
        if (b.stage) {
          const ms = displayMembers(members.filter(m => m.stage_id === b.stage.stage_id));
          summary(data, shapes, ms, y,
            `<h3>${esc(b.stage.label)}</h3><p>${esc(b.stage.summary)}</p><p>${esc(b.stage.boundary_reason)}</p>`,
            null, true);
          y += 54;
          for (const m of ms) {
            const f = fact(m);
            activityRow(data, shapes, f, event, b.stage, y);
            positions.set(m.activity_id, {
              f,
              y
            });
            y += 58;
          }
        } else {
          const f = fact(b.member);
          activityRow(data, shapes, f, event, null, y);
          positions.set(b.member.activity_id, {
            f,
            y
          });
          y += 58;
        }
      }
      for (const r of epg.activity_relation) {
        const a = positions.get(r.from_activity_id),
          b = positions.get(r.to_activity_id);
        if (!a || !b || !a.f.plotTime || !b.f.plotTime) continue;
        const meta = evidenceSets.get(r.evidence_set_id)?.field_metadata || {};
        push(data, {
          type: 'scatter',
          mode: 'lines',
          x: [date(a.f), date(b.f)],
          y: [a.y, b.y],
          line: {
            color: '#78909d',
            width: 1,
            dash: meta.line_style === 'dashed' ? 'dash' : 'solid'
          }
        }, info(linkHover(r)));
      }
      y += 22;
    }
    y += 10;
  }
  const usedActors = new Set([...epg.event_activity.map(m => actor(fact(m))), ...epg.entity_relation
    .flatMap(r => [r.from_entity_id, r.to_entity_id])
  ]);
  for (const id of usedActors) {
    const s = style(id);
    data.push({
      type: 'scatter',
      mode: 'markers',
      x: [null],
      y: [null],
      name: label(id),
      showlegend: true,
      marker: {
        color: s.color,
        symbol: s.symbol,
        size: 8,
        line: {
          color: 'black',
          width: .6
        }
      },
      hoverinfo: 'skip'
    });
  }
  data.push({
    type: 'scatter',
    x: [null],
    y: [null],
    mode: 'lines',
    line: {
      width: 0
    },
    name: '— Relations —',
    showlegend: true,
    hoverinfo: 'skip'
  });
  for (const type of relationTypes) data.push({
    type: 'scatter',
    mode: 'lines',
    x: [null],
    y: [null],
    line: relationStyle(type),
    name: wrap(type, 27),
    showlegend: true,
    hoverinfo: 'skip'
  });
  return {
    data,
    layout: {
      height: Math.max(820, y + 155),
      margin: {
        l: 355,
        r: 250,
        t: 90,
        b: 65
      },
      font: {
        family: 'Arial, Microsoft YaHei, sans-serif',
        size: 14,
        color: '#2a3f5f'
      },
      title: {
        text: esc(label(focal)) + ' · ' + esc(epg.graph.title),
        font: {
          size: 20
        },
        x: .045,
        xanchor: 'left'
      },
      xaxis: {
        type: 'date',
        visible: hasDates,
        domain: [0, .87],
        range: xRange,
        tickformat: '%Y-%m',
        dtick: 'M3',
        showgrid: true,
        gridcolor: '#edf0f4',
        title: {
          text: 'Time'
        },
        fixedrange: false
      },
      xaxis2: {
        domain: [.94, 1],
        type: 'linear',
        range: [-1, 1],
        tickvals: [0],
        ticktext: ['Outside range<br>/ undated'],
        showgrid: false,
        zeroline: false,
        fixedrange: true,
        anchor: 'y'
      },
      yaxis: {
        range: [y, 0],
        showgrid: false,
        zeroline: false,
        showticklabels: false,
        fixedrange: true
      },
      annotations,
      shapes,
      legend: {
        title: {
          text: 'People / organizations'
        },
        x: 1.025,
        y: 1,
        font: {
          size: 13
        }
      },
      hovermode: 'closest',
      hoverlabel: {
        align: 'left',
        font: {
          size: 12
        }
      },
      dragmode: 'pan',
      plot_bgcolor: 'white',
      paper_bgcolor: 'white',
      barmode: 'overlay',
      uirevision: 'reference-person-epg'
    },
    config: {
      responsive: true,
      displaylogo: false,
      scrollZoom: false,
      modeBarButtonsToRemove: ['zoom2d', 'zoomIn2d', 'zoomOut2d', 'autoScale2d', 'resetScale2d',
        'lasso2d', 'select2d'
      ]
    }
  };
}

function toggle(c) {
  if (!c) return;
  const set = c.type === 'domain' ? closedDomains : openEvents;
  set.has(c.id) ? set.delete(c.id) : set.add(c.id);
  queue = queue.then(draw);
}

function draw() {
  const f = build();
  return Plotly.react(gd, f.data, f.layout, f.config);
}
const initial = build();
Plotly.newPlot(gd, initial.data, initial.layout, initial.config).then(() => {
  gd.on('plotly_clickannotation', e => toggle(annotationMap[e.index]));
  gd.on('plotly_click', e => {
    const d = cards[e.points?.[0]?.curveNumber];
    if (d?.control) toggle(d.control);
  });
  gd.on('plotly_relayout', () => {
    if (gd.layout.xaxis?.range) xRange = gd.layout.xaxis.range.slice();
  });
});
document.getElementById('collapse').onclick = () => {
  openEvents.clear();
  closedDomains.clear();
  queue = queue.then(draw);
};
document.getElementById('expand').onclick = () => {
  epg.event.forEach(e => openEvents.add(e.event_id));
  closedDomains.clear();
  queue = queue.then(draw);
};
const scale = document.getElementById('compactness'),
  windowSlider = document.getElementById('time-window');

function updateRange() {
  const duration = Number(scale.value) * DAY,
    left = first - 12 * DAY + Number(windowSlider.value) / 1000 * Math.max(0, (last - first) + 24 *
      DAY - duration);
  xRange = [new Date(left).toISOString(), new Date(left + duration).toISOString()];
  Plotly.relayout(gd, {
    'xaxis.range': xRange
  });
  document.getElementById('scale-label').textContent = scale.value + ' days';
  document.getElementById('time-window-label').textContent = xRange.map(d => d.slice(0, 10)).join(
    ' → ');
}
scale.max = String(Math.ceil((last - first) / DAY + 24));
scale.min = String(Math.min(90, Number(scale.max)));
scale.value = scale.max;
scale.disabled = windowSlider.disabled = !hasDates;
document.getElementById('scale-label').textContent = scale.value + ' days';
document.getElementById('time-window-label').textContent = xRange.map(d => d.slice(0, 10)).join(
  ' → ');
scale.addEventListener('input', updateRange);
windowSlider.addEventListener('input', updateRange);
