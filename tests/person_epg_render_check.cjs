// Exercise the shipped browser script with a minimal DOM/Plotly test double.
// Actual SVG layout and native hover are verified separately in the browser.
const fs = require('node:fs');
const vm = require('node:vm');
const assert = require('node:assert/strict');
const input = JSON.parse(fs.readFileSync(0, 'utf8'));
const elements = new Map();
function element(id) {
  if (!elements.has(id)) elements.set(id, {
    textContent: id === 'epg-data' ? JSON.stringify(input.data) : '',
    value: id === 'time-window' ? '0' : '',
    handlers: {},
    on(name, callback) { this.handlers[name] = callback; },
    addEventListener(name, callback) { this.handlers[name] = callback; }
  });
  return elements.get(id);
}
const gd = element('gantt');
function plot(target, data, layout) {
  Object.assign(target, { data, layout });
  return Promise.resolve(target);
}
const context = vm.createContext({
  document: {getElementById: element},
  Plotly: {
    newPlot: plot, react: plot,
    relayout(target, update) { target.layout.xaxis.range = update['xaxis.range']; }
  }
});
vm.runInContext(fs.readFileSync(input.script, 'utf8'), context);
async function settle() { await vm.runInContext('queue', context); }
const activityTraces = () => gd.data.filter(t => t.meta?.kind === 'activity');
(async () => {
  await settle();
  element('expand').onclick();
  await settle();
  const shown = activityTraces();
  assert.equal(shown.length, input.data.event_activity.length, 'every stored membership appears');
  const expected = input.data.event_activity.map(m => [m.event_id, m.activity_id].join('|')).sort();
  assert.equal(JSON.stringify(shown.map(t => [t.meta.event_id, t.meta.activity_id].join('|')).sort()), JSON.stringify(expected));
  const json = value => JSON.parse(JSON.stringify(value));
  const result = json({
    title: gd.layout.title.text, annotations: gd.layout.annotations,
    data: gd.data, hoverCards: vm.runInContext('cards', context), shapes: gd.layout.shapes, xaxis: gd.layout.xaxis,
    scale: {min: element('compactness').min, max: element('compactness').max,
      disabled: element('compactness').disabled}
  });
  assert.ok(shown.every(t => t.hovertemplate === '%{hovertext}<extra></extra>'));
  const domainIndex = 0;
  gd.handlers.plotly_clickannotation({index: domainIndex});
  await settle();
  const firstDomain = [...input.data.domain].sort((a,b)=>a.sort_order-b.sort_order)[0];
  const closedEvents = new Set(input.data.event.filter(e=>e.domain_id===firstDomain.domain_id).map(e=>e.event_id));
  assert.ok(activityTraces().every(t=>!closedEvents.has(t.meta.event_id)));
  element('collapse').onclick();
  await settle();
  assert.equal(activityTraces().length, 0);
  element('expand').onclick();
  await settle();
  assert.equal(activityTraces().length, expected.length);
  process.stdout.write(JSON.stringify(result));
})().catch(error => { console.error(error); process.exitCode = 1; });
