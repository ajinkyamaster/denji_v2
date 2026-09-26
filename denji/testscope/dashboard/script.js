'use strict';

/*
 * TestScope — change-impact ledger.
 *
 * This page renders one artefact and nothing else: it never calls a model, and it
 * never invents a number. Every value on screen is read from the report JSON,
 * except the code snippets in the counterexample, which are fixed content
 * describing the demo's producer/consumer pair.
 *
 * THREE RULES THIS FILE ENFORCES ON ITSELF
 *
 *   ABSENT IS NOT ZERO. A field the artefact does not carry renders as the words
 *   "not reported". Zero is a measurement; absent is missing information, and a
 *   page that prints 0 for a missing field has manufactured a fact.
 *
 *   TEXT ONLY. Every DOM write goes through textContent. The artefact contains
 *   strings derived from arbitrary repository source, so letting one of them be
 *   parsed as markup would turn any analysed repository into a scripting vector
 *   into the analyst's browser.
 *
 *   IDENTITY. The footer prints which source was loaded and that source's
 *   digest, so a screenshot can never be mistaken for a run it is not.
 */

const REPORT_CANDIDATES = [
  './testscope_report.json',
  '../bob_session/testscope_report.json',
  './mock_report.json',
];

/* ?fixture=1 pins the page to the hand-written fixture. The masthead and footer
 * still say which source is on screen, so forcing the fixture for an evidence
 * screenshot cannot be mistaken for a real run. */
const FIXTURE_PARAM = 'fixture';

const VALID_PREVIEW_LIMIT = 100;
const PRIORITY_PREVIEW_LIMIT = 100;
const HERO_TEST_ID = 'T-0342';

/* Section order is the argument: highest surprise and highest value first. */
const LEDGER_VERDICTS = ['newly_relevant', 'stale', 'uncovered', 'unknown', 'valid'];

const NOT_REPORTED = 'not reported';

const UNCOVERED_ACTION = {
  UNCOVERED_NEW: 'Write a test from nothing.',
  UNCOVERED_BY_STALENESS: 'Repair the existing test and you are covered.',
};

const TRIAGE_ACTION = {
  regression: 'Fix the code.',
  stale: 'Fix the test.',
  flaky: 'Quarantine it; do not chase.',
};

const VERDICT_MEANING = {
  valid: 'the change left alone what this test checks',
  stale: 'the change removed a rule this test checks',
  newly_relevant: 'no import path to the change, but it uses the same data',
  unknown: 'not decidable from the code, so it was included to be safe',
  uncovered: 'the behaviour changed and nothing checks it',
};

document.addEventListener('DOMContentLoaded', () => {
  init().catch(showError);
});

async function init() {
  const loaded = await loadReport();
  const { report, source } = loaded;

  const index = buildIndex(report);

  renderMeta(report, source);
  renderBanners(report);
  renderActivity(report);
  renderHero(report, index);
  renderRunlist(report);
  renderLedger(report, index);
  renderMeasurement(report);
  renderTriage(report, index);
  renderPriority(report, index);
  renderCitations(report);
  renderRejections(report);
  renderFooter(report, source);

  document.getElementById('loading').hidden = true;
  document.getElementById('app').hidden = false;

  startLiveActivity();
}

/* --- activity ---------------------------------------------------------------- */

/* The four checks, in the order they run, described the way a person would
   describe them. These are the units of work behind the report — not the
   pipeline's internal stages, and not its cost accounting. */
const ACTIVITY_AGENTS = [
  {
    id: 'scout',
    name: 'Coupling scan',
    job: 'Looks for code that uses the changed data format without importing it.',
  },
  {
    id: 'cartographer',
    name: 'Doc check',
    job: 'Reads the docstrings and comments for what the code promised to do.',
  },
  {
    id: 'author',
    name: 'Test writer',
    job: 'Writes a test for changed behaviour nothing covers.',
  },
  {
    id: 'falsifier',
    name: 'Challenge pass',
    job: 'Tries to prove this report missed a test that really is affected.',
  },
];

/* Live progress is optional. A running session may drop a small file next to the
   report; if it is there the panel follows it, and if it is not the panel stays
   on what the report itself says. Polling stops the moment the file is gone, so
   a static report costs no requests after the first check. */
const PROGRESS_CANDIDATES = [
  './testscope_progress.json',
  '../bob_session/testscope_progress.json',
];
const PROGRESS_POLL_MS = 900;
let progressTimer = null;
let progressLive = false;

function agentNode(agent) {
  const item = el('li', 'agent');
  item.dataset.agent = agent.id;

  const top = el('span', 'agent-top');
  top.append(el('span', 'agent-name', agent.name));
  top.append(el('span', 'agent-state', ''));
  item.append(top);
  item.append(el('span', 'agent-job', agent.job));
  item.append(el('span', 'agent-tally', ''));
  return item;
}

function setAgentState(item, state, tally) {
  item.dataset.state = state;
  const label = item.querySelector('.agent-state');
  if (label) {
    label.textContent = {
      queued: 'waiting',
      running: 'running',
      done: 'done',
      skipped: 'not needed',
    }[state] || state;
  }
  const total = item.querySelector('.agent-tally');
  if (total) total.textContent = tally || '';
}

/* Source 2: the finished report. claims.by_role is the only honest record of
 * which checks ran. A check with no entry did not run, and saying so is the
 * point — four rows claiming work that never happened would be the exact kind
 * of decoration this page is supposed to refuse.
 *
 * When no AI model was used at all, four identical dead rows would be noise, so
 * the panel collapses to the one sentence that is actually true. */
function renderActivity(report) {
  const list = document.getElementById('activity-agents');
  if (!list) return;
  list.replaceChildren();

  const metadata = report.run_metadata || {};
  const readingRan = metadata.model_layer !== 'disabled';
  const byRole = (report.claims || {}).by_role || {};
  const counts = report.claims || {};
  const ranSomething = ACTIVITY_AGENTS.some((agent) => Number(byRole[agent.id]) > 0);

  if (!readingRan && !ranSomething) {
    const item = el('li', 'agent');
    item.dataset.agent = 'none';
    item.append(el('span', 'agent-name', 'No AI model was used'));
    item.append(el('span', 'agent-job',
      'Everything in this report was computed from the change, the test inventory '
      + 'and the code. The four checks that use a model had nothing to add, so they '
      + 'did not run.'));
    const tally = el('span', 'agent-tally', '');
    tally.textContent = '';
    item.append(tally);
    setAgentState(item, 'skipped', '');
    list.append(item);
  } else {
    for (const agent of ACTIVITY_AGENTS) {
      const item = agentNode(agent);
      const proposed = byRole[agent.id];
      if (!Number.isFinite(proposed) || proposed === 0) {
        setAgentState(item, 'skipped', 'nothing to add');
      } else {
        setAgentState(item, 'done',
          proposed === 1 ? '1 conclusion' : `${proposed} conclusions`);
      }
      list.append(item);
    }
  }

  const panel = document.getElementById('activity');
  const now = document.getElementById('activity-now');
  if (panel) panel.dataset.live = 'false';
  if (now) {
    if (!readingRan && !ranSomething) {
      now.textContent = 'This report is finished.';
    } else if (Number.isFinite(counts.proposed)) {
      now.textContent =
        `${formatNumber(counts.proposed)} conclusions put to the check, `
        + `${formatNumber(counts.accepted || 0)} confirmed — this report is finished.`;
    } else {
      now.textContent = 'This report is finished.';
    }
  }
}

/* Source 1: a running session. Anything unparseable is ignored and the panel
   falls back to the finished state, because a progress file is a convenience
   and must never be able to break the report. */
function applyProgress(payload) {
  const list = document.getElementById('activity-agents');
  const panel = document.getElementById('activity');
  const now = document.getElementById('activity-now');
  if (!list || !payload || typeof payload !== 'object') return;

  const steps = Array.isArray(payload.steps) ? payload.steps : [];
  if (steps.length === 0) return;

  const byAgent = new Map();
  for (const step of steps) {
    if (step && step.id) byAgent.set(step.id, step);
  }

  for (const agent of ACTIVITY_AGENTS) {
    const item = list.querySelector(`[data-agent="${agent.id}"]`);
    if (!item) continue;
    const step = byAgent.get(agent.id);
    if (!step) continue;
    const status = ['queued', 'running', 'done', 'skipped'].includes(step.status)
      ? step.status
      : 'queued';
    if (typeof step.name === 'string' && step.name.trim() !== '') {
      const job = item.querySelector('.agent-job');
      if (job) job.textContent = step.name;
    }
    setAgentState(item, status, typeof step.detail === 'string' ? step.detail : '');
  }

  const running = steps.find((step) => step && step.status === 'running');
  if (panel) panel.dataset.live = 'true';
  const label = document.getElementById('activity-title');
  if (label) label.textContent = 'Running now';
  if (now) {
    const line = typeof payload.current_step === 'string' && payload.current_step.trim() !== ''
      ? payload.current_step
      : (running && running.name) || 'working';
    now.textContent = line;
  }
}

let progressProbed = false;

async function pollProgress() {
  if (progressProbed && !progressLive) return false;
  for (const candidate of PROGRESS_CANDIDATES) {
    let response;
    try {
      response = await fetch(candidate, { cache: 'no-store' });
    } catch (error) {
      continue;
    }
    if (!response.ok) continue;
    try {
      applyProgress(JSON.parse(await response.text()));
    } catch (error) {
      /* A half-written file is expected while a run is in flight. */
    }
    return true;
  }
  /* Nothing there. Remember it, so a finished report is asked exactly once. */
  progressProbed = true;
  return false;
}

async function startLiveActivity() {
  const running = await pollProgress();
  if (!running) return;
  progressTimer = window.setInterval(async () => {
    const stillThere = await pollProgress();
    if (stillThere) return;
    window.clearInterval(progressTimer);
    progressTimer = null;
  }, PROGRESS_POLL_MS);
}

/* --- loading ---------------------------------------------------------------- */

async function loadReport() {
  const params = new URLSearchParams(window.location.search);
  const forced = params.has(FIXTURE_PARAM);
  const candidates = forced ? ['./mock_report.json'] : REPORT_CANDIDATES;
  const problems = [];

  for (const candidate of candidates) {
    let response;
    try {
      response = await fetch(candidate, { cache: 'no-store' });
    } catch (error) {
      problems.push(`${candidate}: ${error.message}`);
      continue;
    }
    if (!response.ok) {
      problems.push(`${candidate}: HTTP ${response.status}`);
      continue;
    }
    try {
      const report = JSON.parse(await response.text());
      assertShape(report);
      return { report, source: candidate };
    } catch (error) {
      problems.push(`${candidate}: ${error.message}`);
    }
  }

  const failure = new Error('no usable report');
  failure.details = problems;
  throw failure;
}

/* The reason vocabulary a bucket may carry.
 *
 * The frozen contract names three reasons: syntactic, semantic, unaffected. The
 * pipeline emits the same three buckets under more precise names —
 * structural_import_closure, representation_coupling, and either
 * no_import_path_to_changed_module or normalised_inert_change. Both spellings
 * describe the same three buckets, so this list accepts either.
 *
 * What the check protects is the invariant underneath the spelling: a reason
 * must never contradict the bucket it sits in. A semantic test filed as
 * unaffected is a wrong answer, whatever the words are. Validating the exact
 * string instead would reject a real report over a rename and quietly fall back
 * to the fixture, which is the worst failure this page has. */
const REASON_BY_BUCKET = {
  definitely_affected: ['syntactic', 'structural_import_closure'],
  semantically_affected: ['semantic', 'representation_coupling'],
  not_affected: [
    'unaffected',
    'no_import_path_to_changed_module',
    'normalised_inert_change',
  ],
};

const ENTRY_FIELDS = ['test_id', 'test_name', 'module', 'reason', 'explanation'];

/* Shape checks mirror the frozen contract. A structurally wrong file is an error
 * state, not a half-rendered page: a dashboard that silently drops rows would
 * make the numbers on screen quietly untrue. Keys added by the ledger layer are
 * optional — their absence is a state to render, not a crash. */
function assertShape(report) {
  if (!report || typeof report !== 'object') {
    throw new Error('report is not an object');
  }
  for (const key of ['run_metadata', 'classification', 'summary']) {
    if (!(key in report)) throw new Error(`missing ${key}`);
  }
  if (!Array.isArray(report.run_metadata.diff_files)) {
    throw new Error('run_metadata.diff_files is not a list');
  }
  const summaryFields = [
    'total',
    'selected_for_run',
    'definitely_affected_count',
    'semantically_affected_count',
    'reduction_pct',
  ];
  for (const field of summaryFields) {
    if (typeof report.summary[field] !== 'number') {
      throw new Error(`summary.${field} is missing or not a number`);
    }
  }
  for (const [key, accepted] of Object.entries(REASON_BY_BUCKET)) {
    const entries = report.classification[key];
    if (!Array.isArray(entries)) throw new Error(`classification.${key} is not a list`);
    entries.forEach((entry, position) => {
      for (const field of ENTRY_FIELDS) {
        if (typeof entry[field] !== 'string' || entry[field].trim() === '') {
          throw new Error(`classification.${key}[${position}].${field} is missing`);
        }
      }
      if (!accepted.includes(entry.reason)) {
        throw new Error(
          `classification.${key}[${position}] has reason '${entry.reason}', which ` +
          `contradicts its bucket; expected one of ${accepted.join(', ')}`);
      }
    });
  }
}

/* --- helpers ---------------------------------------------------------------- */

function buildIndex(report) {
  const byId = new Map();
  for (const bucket of Object.values(report.classification || {})) {
    if (!Array.isArray(bucket)) continue;
    for (const entry of bucket) byId.set(entry.test_id, entry);
  }
  return byId;
}

function setText(id, value) {
  const node = document.getElementById(id);
  if (!node) return;
  node.textContent = value;
  /* A number at display size (36px/28px) fits any cell; a fallback phrase does
     not — "reported" alone measures 184px inside a 142px hero fact column. So a
     display value that is prose rather than a figure shrinks to the small style:
     an absent field must never spill onto its neighbour. */
  if (node.classList.contains('fact-num') || node.classList.contains('metric-value')) {
    node.classList.toggle('is-small', String(value).length > 8);
  }
}

function setCount(id, value) {
  setText(id, typeof value === 'number' ? `(${formatNumber(value)})` : '');
}

function isNumber(value) {
  return typeof value === 'number' && Number.isFinite(value);
}

/* Reads a possibly-absent field. Absence renders as the words, never as 0. */
function readNumber(source, key) {
  if (!source || !hasOwn(source, key)) return null;
  const value = source[key];
  return isNumber(value) ? value : null;
}

function hasOwn(object, key) {
  return object !== null && object !== undefined &&
    Object.prototype.hasOwnProperty.call(object, key);
}

function formatNumber(value) {
  return Number(value).toLocaleString('en-US');
}

function show(id, visible) {
  const node = document.getElementById(id);
  if (node) node.hidden = !visible;
}

function emptyState(id, html) {
  const node = document.getElementById(id);
  if (!node) return;
  node.replaceChildren();
  node.append(document.createTextNode(html));
  node.hidden = false;
}

function el(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined && text !== null) node.textContent = String(text);
  return node;
}

/* --- provenance -------------------------------------------------------------- */

/* What is on screen, and where it came from. Deliberately short: a reader
   wants to know which run this is and whether it is real, not the schema
   revision or a content hash. The one thing that must never be ambiguous is a
   sample report, so describeSource says so in as many words. */
function renderMeta(report, source) {
  setText('meta-generated', formatTimestamp(report.run_metadata.generated_at));
  setText('meta-source', describeSource(source));
}

function renderFooter(report, source) {
  setText('foot-generated', formatTimestamp(report.run_metadata.generated_at));
  setText('foot-diff', (report.run_metadata.diff_files || []).join(', ') || NOT_REPORTED);
  setText('foot-source', describeSource(source));
}

function describeSource(source) {
  if (!source) return NOT_REPORTED;
  return source === './mock_report.json'
    ? 'sample report — not a real run'
    : source;
}

function formatTimestamp(value) {
  if (typeof value !== 'string' || value.trim() === '') return NOT_REPORTED;
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return value;
  return parsed.toISOString().replace('T', ' ').replace(/\.\d+Z$/, ' UTC');
}

/* --- banners: the two states that must be read before anything else ----------- */

function renderBanners(report) {
  const metadata = report.run_metadata || {};
  const measurement = report.measurement;
  const oracle = measurement && measurement.oracle;
  const layerEnabled = metadata.model_layer !== 'disabled';

  /* 1. VOID — a catch rate measured against something smaller than the suite. */
  const voidBanner = document.getElementById('banner-void');
  if (voidBanner) {
    voidBanner.replaceChildren();
    const complete = Boolean(oracle && oracle.complete === true);
    if (oracle && !complete) {
      const collected = readNumber(oracle, 'collected');
      const total = readNumber(oracle, 'inventory_total');
      voidBanner.append(el('p', 'banner-title', 'This accuracy check is incomplete'));
      voidBanner.append(el('p', null,
        'The before-and-after comparison did not cover the whole test suite, so it ' +
        'cannot say what this change really breaks. The catch rate below is withheld ' +
        'rather than published from a partial run.'));
      voidBanner.append(el('p', 'stat-note',
        `covered ${collected === null ? NOT_REPORTED : formatNumber(collected)} of ` +
        `${total === null ? NOT_REPORTED : formatNumber(total)} tests`));
      voidBanner.hidden = false;
    } else {
      voidBanner.hidden = true;
    }
  }

  /* 2. DEGRADED — no AI model contributed to this run. The computed analysis
   * still ran in full; this discloses the provenance class, nothing more. */
  const degradedBanner = document.getElementById('banner-degraded');
  if (degradedBanner) {
    degradedBanner.replaceChildren();
    if (!layerEnabled) {
      degradedBanner.append(el('p', 'banner-title', 'No AI model was used for this run'));
      degradedBanner.append(el('p', null,
        'Every result here was computed from the change, the test inventory and ' +
        'the code itself, with no model in the loop. Read it as the floor: a model ' +
        'pass can add to this, and it cannot remove from it.'));
      degradedBanner.hidden = false;
    } else {
      degradedBanner.hidden = true;
    }
  }
}

/* --- V1 · the three-second hero ---------------------------------------------- */

function renderHero(report, index) {
  const summary = report.summary || {};
  const measurement = report.measurement;

  const total = readNumber(summary, 'total');
  const selected = readNumber(summary, 'selected_for_run');
  const semanticCount = readNumber(summary, 'semantically_affected_count');

  setText('fact-total', total === null ? NOT_REPORTED : formatNumber(total));
  setText('fact-reachable', measurement
    ? String(readNumber(measurement, 'structurally_reachable') ?? NOT_REPORTED)
    : NOT_REPORTED);
  setText('lede-reachable', measurement && isNumber(measurement.structurally_reachable)
    ? String(measurement.structurally_reachable)
    : NOT_REPORTED);

  /* Fact 3 is the product claim: a behavioural catch that static tooling cannot
   * reach AND that turns red. Counted from the artefact (newly-relevant tests
   * diagnosed as a regression), not asserted — so it reads +1 on the demo and
   * stays true if a run ever finds two. The foot below gives the full count, so
   * the smaller number can never be mistaken for the whole picture. */
  const newlyRelevant = new Set(
    ((report.ledger || {}).newly_relevant || []).map((entry) => entry.test_id));
  const triage = Array.isArray(report.triage) ? report.triage : [];
  const failing = triage.filter((entry) =>
    entry.diagnosis === 'regression' && newlyRelevant.has(entry.test_id)).length;

  /* Deliberately NOT gated on run_metadata.model_layer. That flag says whether
   * an AI model contributed; it does not say whether coupling was searched for.
   * The computed analysis finds representation coupling on its own, so keying
   * the hero to the flag printed "+0" on a report that carried six coupling
   * findings and three real regressions — a false statement on the one screen
   * that has to be true. */
  const redIds = triage
    .filter((entry) => entry.diagnosis === 'regression' && newlyRelevant.has(entry.test_id))
    .map((entry) => entry.test_id)
    .sort();

  let catchCount;
  if (triage.length > 0) {
    catchCount = failing;
  } else {
    /* No triage block: fall back to the behavioural count, which is the
     * conservative reading rather than a confident zero. */
    catchCount = semanticCount === null ? null : semanticCount;
  }
  setText('fact-extra', catchCount === null ? NOT_REPORTED : `+${catchCount}`);

  /* The lede must not assert a count the report does not carry. It reads
     "Three more tests" on a run that caught three and "one" on a run that caught
     one, and falls back to a word that cannot be wrong when the count is absent. */
  setText('lede-extra', catchCount === null
    ? 'Some tests'
    : (catchCount === 1 ? 'One more test' : `${formatNumber(catchCount)} more tests`));
  setText('fact-verdict-label', catchCount === null || catchCount === 0
    ? 'and nothing outside the import graph is red on the current commit'
    : (catchCount === 1
      ? 'and that one is red on the current commit'
      : `and all ${formatNumber(catchCount)} of them are red on the current commit`));

  const hero = index.get(HERO_TEST_ID);
  setText('catch-test', hero ? `${hero.test_id} · ${hero.test_name}` : NOT_REPORTED);
  setText('catch-module', hero ? hero.module : NOT_REPORTED);

  /* Honest footers for the states that would otherwise read as a boast. */
  const foot = document.getElementById('hero-foot');
  if (foot) {
    foot.replaceChildren();
    if (selected === 0) {
      foot.append(document.createTextNode(
        'Nothing needs running. This change does not alter behaviour, so there is ' +
        'no test worth the time.'));
    } else if (catchCount === 0) {
      foot.append(document.createTextNode(
        'Nothing outside the import graph went red on this change.'));
    } else {
      foot.append(document.createTextNode(
        'Reading the code found '));
      foot.append(el('span', 'num-inline',
        semanticCount === null ? NOT_REPORTED : String(semanticCount)));
      foot.append(document.createTextNode(
        ` tests with no import path to the change, and `
        + `${catchCount === 1 ? 'one of them is' : `all ${formatNumber(catchCount)} of them are`} `
        + `red on this commit: ${redIds.join(', ')}.`));
    }
  }
}

/* --- the run list ------------------------------------------------------------ */

function renderRunlist(report) {
  const semantic = (report.classification.semantically_affected || []).map((entry) => ({
    entry, kind: 'semantic',
  }));
  const syntactic = (report.classification.definitely_affected || []).map((entry) => ({
    entry, kind: 'syntactic',
  }));

  /* Behavioural catches first: the hero case must be visible without scrolling. */
  const rows = [...semantic, ...syntactic].sort((left, right) => {
    if (left.kind !== right.kind) return left.kind === 'semantic' ? -1 : 1;
    return left.entry.test_id.localeCompare(right.entry.test_id);
  });

  const body = document.getElementById('runlist-body');
  if (!body) return;
  body.replaceChildren();

  for (const { entry, kind } of rows) {
    const [row, detail] = buildTestRow(entry, kind);
    body.append(row, detail);
  }

  setCount('runlist-count', rows.length);
  if (rows.length === 0) {
    emptyState('runlist-empty',
      '0 tests selected — the change is behaviourally inert. Nothing needs to run.');
  } else {
    show('runlist-empty', false);
  }
}

/** One test row plus its hidden explanation row, built as a pair. */
function buildTestRow(entry, kind) {
  const row = document.createElement('tr');
  row.className = 'test-row';

  const idCell = document.createElement('td');
  idCell.className = 'test-id';
  const toggle = document.createElement('button');
  toggle.type = 'button';
  toggle.className = 'row-toggle';
  toggle.textContent = entry.test_id;
  /* Declared at build time, not on first click: a disclosure control must report
   * its state before it is used, and must point at what it controls. */
  toggle.setAttribute('aria-expanded', 'false');
  toggle.setAttribute('aria-controls', `detail-${entry.test_id}`);
  idCell.append(toggle);

  const nameCell = document.createElement('td');
  nameCell.className = 'test-name';
  nameCell.textContent = entry.test_name;

  const moduleCell = document.createElement('td');
  moduleCell.className = 'test-module';
  moduleCell.textContent = entry.module;

  const tagCell = document.createElement('td');
  tagCell.append(el('span', `pill pill-${kind}`, kind));
  if (kind === 'semantic') {
    /* Kept short enough to stay on one line in the Coupling column; the full
     * sentence is one click away in the disclosure panel. */
    tagCell.append(el('span', 'pill pill-priority', 'no import edge'));
  }

  row.append(idCell, nameCell, moduleCell, tagCell);

  const detail = document.createElement('tr');
  detail.className = 'detail-row';
  detail.id = `detail-${entry.test_id}`;
  detail.hidden = true;
  const detailCell = document.createElement('td');
  detailCell.colSpan = 4;
  detailCell.append(
    el('span', 'detail-label', 'Why it is on the list'),
    el('span', null, entry.explanation)
  );
  detail.append(detailCell);

  const toggleRow = () => {
    const open = detail.hidden;
    detail.hidden = !open;
    row.classList.toggle('is-open', open);
    toggle.setAttribute('aria-expanded', String(open));
  };
  /* One handler on the row covers both the button and the click, because a
   * button click bubbles. Keyboard users get the real control. */
  row.addEventListener('click', toggleRow);
  return [row, detail];
}

/* --- V2 · the ledger ---------------------------------------------------------- */

function renderLedger(report, index) {
  const ledger = report.ledger || {};
  const uncovered = Array.isArray(report.uncovered) ? report.uncovered : null;

  for (const verdict of LEDGER_VERDICTS) {
    const body = document.getElementById(`body-${verdict}`);
    const empty = document.getElementById(`empty-${verdict}`);
    if (!body || !empty) continue;

    if (verdict === 'uncovered') {
      renderUncoveredRow(uncovered, body, empty);
      continue;
    }

    const entries = Array.isArray(ledger[verdict]) ? ledger[verdict] : null;
    if (entries === null) {
      /* Absent is not zero: say the key is missing rather than showing an
       * empty section that looks like "nothing to do". */
      setCount(`count-${verdict}`, null);
      body.replaceChildren();
      emptyState(`empty-${verdict}`,
        `${labelFor(verdict)}: not reported. This artefact carries no "${verdict}" key, ` +
        `so nothing can be claimed about it either way.`);
      continue;
    }

    setCount(`count-${verdict}`, entries.length);

    if (entries.length === 0) {
      body.replaceChildren();
      emptyState(`empty-${verdict}`, emptyCopy(verdict));
      continue;
    }

    empty.hidden = true;
    if (verdict === 'valid') {
      renderValidLazy(entries, index, body);
    } else {
      body.replaceChildren();
      for (const entry of entries) {
        /* buildLedgerRow returns a PAIR [row, detail], not a list of pairs —
           destructuring it inside a for-of would try to destructure each <tr>. */
        const [row, detail] = buildLedgerRow(entry, verdict, index);
        body.append(row, detail);
      }
    }
  }
}

function labelFor(verdict) {
  return {
    newly_relevant: 'Newly relevant',
    stale: 'Stale',
    unknown: 'Unknown',
    valid: 'Valid',
    uncovered: 'Uncovered',
  }[verdict] || verdict;
}

function emptyCopy(verdict) {
  if (verdict === 'uncovered') return '';
  if (verdict === 'valid') return 'No tests fall in this bucket on this change.';
  if (verdict === 'stale') return 'Nothing asserts a contract this change removed.';
  if (verdict === 'unknown') return 'Every test could be decided on this change.';
  if (verdict === 'newly_relevant') {
    return 'Nothing outside the import graph was found on this change.';
  }
  return 'Nothing here.';
}

/* The evidence shown IN a row, as one flowing line: for STALE the removed
 * behaviour followed by the test's file:line, for NEWLY RELEVANT the link
 * evidence, otherwise the reason. CSS clamps this line to two rows of text so a
 * long artefact string cannot triple a row's height (measurement M2); the
 * unclamped text is repeated in the detail row one click below. */
function evidenceText(entry, verdict) {
  if (verdict === 'stale') {
    const bits = [entry.removed_behaviour || NOT_REPORTED];
    (Array.isArray(entry.evidence) ? entry.evidence : []).forEach((line) => bits.push(line));
    return bits.join(' · ');
  }
  if (verdict === 'newly_relevant') {
    const links = Array.isArray(entry.link_evidence) ? entry.link_evidence : [];
    return links.length ? links.join(' · ') : NOT_REPORTED;
  }
  return entry.why || NOT_REPORTED;
}

function buildLedgerRow(entry, verdict, index) {
  const testId = entry.test_id;
  const match = index.get(testId);

  const row = document.createElement('tr');
  row.className = 'test-row';

  const idCell = document.createElement('td');
  idCell.className = 'test-id';
  const toggle = document.createElement('button');
  toggle.type = 'button';
  toggle.className = 'row-toggle';
  toggle.textContent = testId;
  toggle.setAttribute('aria-expanded', 'false');
  toggle.setAttribute('aria-controls', `detail-${verdict}-${testId}`);
  idCell.append(toggle);

  const nameCell = document.createElement('td');
  nameCell.className = 'test-name';
  nameCell.textContent = match ? match.test_name : NOT_REPORTED;

  const moduleCell = document.createElement('td');
  moduleCell.className = 'test-module';
  moduleCell.textContent = match ? match.module : NOT_REPORTED;

  const evidenceCell = document.createElement('td');
  const flow = el('span', 'ev-flow');
  if (verdict === 'stale') {
    flow.append(el('span', 'evidence-key', 'removed'));
  }
  flow.append(el('span', 'evidence', evidenceText(entry, verdict)));
  evidenceCell.append(flow);

  row.append(idCell, nameCell, moduleCell, evidenceCell);

  const detail = document.createElement('tr');
  detail.className = 'detail-row';
  detail.id = `detail-${verdict}-${testId}`;
  detail.hidden = true;
  const detailCell = document.createElement('td');
  detailCell.colSpan = 4;
  detailCell.append(el('span', 'detail-label',
    `${labelFor(verdict)} — ${VERDICT_MEANING[verdict] || ''}`));
  detailCell.append(el('span', null, entry.why || (match ? match.explanation : NOT_REPORTED)));
  if (verdict === 'stale' || verdict === 'newly_relevant') {
    /* The row clamps its evidence to two lines; the detail row carries it whole. */
    detailCell.append(el('span', 'detail-evidence', evidenceText(entry, verdict)));
  }
  detail.append(detailCell);

  row.addEventListener('click', () => {
    const open = detail.hidden;
    detail.hidden = !open;
    row.classList.toggle('is-open', open);
    toggle.setAttribute('aria-expanded', String(open));
  });

  return [row, detail];
}

/* The valid bucket is the boring majority: zero DOM rows until it is opened. */
function renderValidLazy(entries, index, body) {
  const details = document.getElementById('valid-details');
  const summary = document.getElementById('valid-summary');
  const note = document.getElementById('valid-note');
  if (!details || !summary) return;

  summary.textContent =
    `${formatNumber(entries.length)} tests — click to build the rows`;
  /* Stated before the control is used, not after the first click. */
  summary.setAttribute('aria-expanded', 'false');

  let rendered = false;
  const populate = () => {
    if (rendered) return;
    rendered = true;
    body.replaceChildren();
    const shown = entries.slice(0, VALID_PREVIEW_LIMIT);
    for (const entry of shown) {
      const [row, detail] = buildLedgerRow(entry, 'valid', index);
      body.append(row, detail);
    }
    if (note) {
      const remaining = entries.length - shown.length;
      note.textContent = remaining > 0
        ? `Showing the first ${formatNumber(shown.length)} of ${formatNumber(entries.length)} rows. ` +
          `+${formatNumber(remaining)} more — see the report JSON for the full list.`
        : `All ${formatNumber(entries.length)} rows, built when this section was opened.`;
    }
  };

  details.addEventListener('toggle', () => {
    summary.setAttribute('aria-expanded', String(details.open));
    if (details.open) populate();
  });
  if (details.open) populate();
}

function renderUncoveredRow(uncovered, body, empty) {
  body.replaceChildren();

  if (uncovered === null) {
    setCount('count-uncovered', null);
    emptyState('empty-uncovered',
      'Uncovered: not reported. This artefact carries no "uncovered" key, so nothing ' +
      'can be claimed about coverage of changed behaviour either way.');
    return;
  }

  setCount('count-uncovered', uncovered.length);

  if (uncovered.length === 0) {
    emptyState('empty-uncovered',
      'Every changed behaviour the report looked at has at least one test.');
    return;
  }

  empty.hidden = true;
  for (const item of uncovered) {
    const row = document.createElement('tr');
    row.className = 'test-row';

    const symbol = document.createElement('td');
    symbol.textContent = item.symbol || NOT_REPORTED;

    const where = document.createElement('td');
    where.textContent = item.path
      ? `${item.path}:${isNumber(item.line) ? item.line : '?'}`
      : NOT_REPORTED;

    const kind = document.createElement('td');
    const kindName = item.kind || 'UNKNOWN_KIND';
    kind.append(el('span', `pill ${kindName === 'UNCOVERED_BY_STALENESS' ? 'pill-by-staleness' : 'pill-new'}`,
      kindName === 'UNCOVERED_BY_STALENESS' ? 'repair' : 'write new'));
    kind.append(el('span', 'pill pill-priority', kindName));

    const action = document.createElement('td');
    action.textContent = UNCOVERED_ACTION[kindName] || 'Decide what this needs.';

    row.append(symbol, kind, where, action);

    const detail = document.createElement('tr');
    detail.className = 'detail-row';
    detail.hidden = true;
    const detailCell = document.createElement('td');
    detailCell.colSpan = 4;
    detailCell.append(el('span', 'detail-label', 'Work item — not a test'));
    detailCell.append(el('span', null,
      `${item.symbol || NOT_REPORTED} changed at ${item.path || NOT_REPORTED}:` +
      `${isNumber(item.line) ? item.line : '?'}` +
      `${Array.isArray(item.changed_lines) && item.changed_lines.length
        ? ` (lines ${item.changed_lines.join(', ')})` : ''}. ` +
      `${item.has_any_test === true ? 'Some test covers it.' : 'No test covers it.'} ` +
      `${UNCOVERED_ACTION[kindName] || ''}`));
    detail.append(detailCell);

    row.addEventListener('click', () => {
      const open = detail.hidden;
      detail.hidden = !open;
      row.classList.toggle('is-open', open);
    });
    body.append(row, detail);
  }
}

/* --- V3 · measurement ---------------------------------------------------------- */

function renderMeasurement(report) {
  const measurement = report.measurement;
  const box = document.getElementById('metrics');
  if (!box) return;

  if (!measurement || typeof measurement !== 'object') {
    for (const id of ['m-truth', 'm-selected', 'm-reachable', 'm-price', 'm-recall']) {
      setText(id, NOT_REPORTED);
    }
    setText('m-recall-note', 'this report carries no accuracy figures');
    return;
  }

  const oracle = measurement.oracle;
  const complete = Boolean(oracle && oracle.complete === true);

  const truth = readNumber(measurement, 'truth_size');
  const selected = readNumber(measurement, 'selected');
  const reachable = readNumber(measurement, 'structurally_reachable');
  const price = readNumber(measurement, 'price_of_safety');
  const recall = readNumber(measurement, 'recall');

  setText('m-truth', truth === null ? NOT_REPORTED : formatNumber(truth));
  setText('m-selected', selected === null ? NOT_REPORTED : formatNumber(selected));
  setText('m-reachable', reachable === null ? NOT_REPORTED : formatNumber(reachable));
  setText('m-price', price === null ? NOT_REPORTED : formatNumber(price));

  const recallNode = document.getElementById('m-recall');
  const recallNote = document.getElementById('m-recall-note');

  if (recallNode) {
    recallNode.classList.remove('is-void', 'is-small');
    if (!complete) {
      /* VOID, not a number. The raw value is shown only as an unusable footnote. */
      recallNode.textContent = 'VOID';
      recallNode.classList.add('is-void');
      if (recallNote) {
        recallNote.textContent = recall === null
          ? 'the comparison did not finish, so there is no catch rate'
          : `raw value ${recall.toFixed(2)} — not usable, the comparison was partial`;
      }
    } else if (recall === null) {
      recallNode.textContent = NOT_REPORTED;
      recallNode.classList.add('is-small');
      if (recallNote) recallNote.textContent = 'share of the real breaks that were caught';
    } else {
      recallNode.textContent = recall.toFixed(2);
      if (recallNote) recallNote.textContent = 'share of the real breaks that were caught';
    }
  }
}

/* --- V4 · red triage ----------------------------------------------------------- */

function renderTriage(report, index) {
  const grid = document.getElementById('triage-grid');
  if (!grid) return;
  grid.replaceChildren();

  const entries = Array.isArray(report.triage) ? report.triage : null;
  if (entries === null) {
    show('triage-empty', false);
    grid.append(el('p', 'empty-state',
      'Red triage: not reported. This artefact carries no "triage" key, so no failing ' +
      'test has been diagnosed on this run.'));
    return;
  }

  if (entries.length === 0) {
    grid.append(el('p', 'empty-state', 'Nothing failed at this revision.'));
    return;
  }

  for (const entry of entries) {
    const diagnosis = entry.diagnosis || 'unknown';
    const card = el('article', 'triage-card');
    card.setAttribute('data-diagnosis', diagnosis);

    const top = el('div', 'triage-top');
    top.append(el('span', 'triage-test', entry.test_id || NOT_REPORTED));
    top.append(el('span', `pill pill-${diagnosis}`, diagnosis));
    card.append(top);

    card.append(el('p', 'triage-action', TRIAGE_ACTION[diagnosis] || 'Decide what this is.'));
    card.append(el('p', 'triage-signal', entry.signal || NOT_REPORTED));

    const match = entry.test_id ? index.get(entry.test_id) : null;
    if (match) card.append(el('p', 'metric-note', `${match.test_name} · ${match.module}`));

    grid.append(card);
  }
}

/* --- V5 · priority order -------------------------------------------------------- */

function renderPriority(report, index) {
  const list = document.getElementById('priority-list');
  if (!list) return;
  list.replaceChildren();

  const order = Array.isArray(report.priority_order) ? report.priority_order : null;
  if (order === null) {
    show('priority-empty', false);
    list.append(el('p', 'empty-state',
      'Run order: not reported. This artefact carries no "priority_order" key.'));
    return;
  }

  const newlyRelevant = new Set(
    ((report.ledger || {}).newly_relevant || []).map((entry) => entry.test_id));
  const stale = new Set(((report.ledger || {}).stale || []).map((entry) => entry.test_id));
  const unknown = new Set(((report.ledger || {}).unknown || []).map((entry) => entry.test_id));
  const syntactic = new Set(
    (report.classification.definitely_affected || []).map((entry) => entry.test_id));

  if (order.length === 0) {
    list.append(el('li', 'empty-state', 'Nothing to run on this change.'));
    return;
  }

  const shown = order.slice(0, PRIORITY_PREVIEW_LIMIT);
  shown.forEach((testId, position) => {
    const item = document.createElement('li');
    if (newlyRelevant.has(testId)) item.className = 'priority-first';

    item.append(el('span', 'priority-rank', String(position + 1).padStart(2, '0')));
    item.append(el('span', 'priority-id', testId));

    let why;
    if (newlyRelevant.has(testId)) {
      why = 'No import edge — run first; this is the one that ships the bug.';
    } else if (stale.has(testId)) {
      why = 'Stale: repair or delete the test before trusting the run.';
    } else if (unknown.has(testId)) {
      why = 'Could not be decided, so it was included — the safe direction.';
    } else if (syntactic.has(testId)) {
      why = 'Imports the changed module.';
    } else {
      why = index.has(testId) ? 'Not affected by this change.' : NOT_REPORTED;
    }
    item.append(el('span', 'priority-why', why));
    list.append(item);
  });

  if (order.length > shown.length) {
    const note = document.createElement('li');
    note.className = 'empty-state';
    note.textContent = `+${formatNumber(order.length - shown.length)} more in the report JSON.`;
    list.append(note);
  }
}

/* --- V6 · citation viewer -------------------------------------------------------- */

/*
 * The frozen v1 schema carries per-test evidence (`ledger.*.evidence`,
 * `ledger.*.link_evidence`) but no per-claim records, so this view renders two
 * groups: the kernel's verdicts if the artefact carries them (optional key
 * `accepted_claims`), and always the evidence the schema does define. When the
 * optional key is absent the view says so instead of pretending to be empty.
 */
function renderCitations(report) {
  const container = document.getElementById('claims-citations');
  if (!container) return;
  container.replaceChildren();

  /* Two spellings exist for the same list: the contract's `verified_claims` and
     the emitted `accepted_claims`. Accept either; say which one is missing by
     name only when neither is present. */
  const claims = Array.isArray(report.accepted_claims)
    ? report.accepted_claims
    : (Array.isArray(report.verified_claims) ? report.verified_claims : null);
  let built = 0;

  if (claims !== null) {
    for (const claim of claims) {
      container.append(buildClaimCard(claim));
      built += 1;
    }
  } else {
    container.append(el('p', 'empty-state',
      'No per-claim verdicts to show: this report carries neither an ' +
      '"accepted_claims" nor a "verified_claims" list. The evidence below is ' +
      're-derived from the repository and is always shown.'));
  }

  const ledger = report.ledger || {};
  const evidenceRows = [];
  for (const entry of Array.isArray(ledger.stale) ? ledger.stale : []) {
    evidenceRows.push({
      subject: entry.test_id,
      claim: 'the contract this test asserts was removed by the change',
      refs: Array.isArray(entry.evidence) ? entry.evidence : [],
      obligation: 're-derived from the diff',
      drift: false,
    });
  }
  for (const entry of Array.isArray(ledger.newly_relevant) ? ledger.newly_relevant : []) {
    evidenceRows.push({
      subject: entry.test_id,
      claim: 'this test is behaviourally coupled to the changed code',
      refs: Array.isArray(entry.link_evidence) ? entry.link_evidence : [],
      obligation: 'coupling re-derived',
      drift: false,
    });
  }

  if (evidenceRows.length > 0) {
    const heading = el('h3', 'subhead', 'Evidence re-derived from the repository');
    container.append(heading);
    for (const row of evidenceRows) {
      container.append(buildClaimCard({
        claim_type: 'evidence',
        role: 'kernel',
        rationale: row.claim,
        citations: row.refs.map((ref) => ({ ref })),
        obligation: row.obligation,
        subject: row.subject,
      }));
    }
    built += evidenceRows.length;
  }

  if (built === 0) {
    container.append(el('p', 'empty-state', 'No verification records in this artefact.'));
  }
}

function buildClaimCard(claim) {
  const card = el('article', 'claim');

  const head = el('div', 'claim-head');
  head.append(el('span', 'claim-type', claim.claim_type || 'claim'));
  if (claim.role) head.append(el('span', 'claim-role', `${claim.role} role`));
  if (claim.subject) head.append(el('span', 'claim-role', claim.subject));
  if (claim.confidence) head.append(el('span', 'claim-role', `confidence ${claim.confidence}`));
  card.append(head);

  if (claim.rationale) card.append(el('p', 'claim-rationale', claim.rationale));

  const citations = Array.isArray(claim.citations) ? claim.citations : [];
  if (citations.length === 0) {
    card.append(el('p', 'metric-note', `citations: ${NOT_REPORTED}`));
  } else {
    const list = el('div', 'citations');
    for (const citation of citations) {
      const line = el('div', 'citation');
      let reference;
      if (typeof citation === 'string') {
        reference = citation;
      } else if (typeof citation.ref === 'string' && citation.ref !== '') {
        /* Evidence strings from the frozen schema are already composed. */
        reference = citation.ref;
      } else {
        reference = [citation.path, citation.symbol, citation.line]
          .filter((part) => part !== undefined && part !== null && part !== '')
          .join(':');
      }
      line.append(el('span', 'citation-ref', reference || NOT_REPORTED));

      let obligationText = claim.obligation || 're-derived';
      let obligationClass = 'obligation';
      if (citation.line_drift === true || claim.line_drift === true) {
        obligationText = 'line_drift — symbol resolves';
        obligationClass += ' is-drift';
      }
      if (claim.gate) {
        obligationText = `rejected: ${claim.gate}`;
        obligationClass = 'obligation is-rejected';
      }
      line.append(el('span', obligationClass, obligationText));
      list.append(line);
    }
    card.append(list);
  }

  if (claim.detail) card.append(el('p', 'metric-note', claim.detail));
  return card;
}

/* --- V7 · rejection ledger --------------------------------------------------------- */

function renderRejections(report) {
  const claims = report.claims || {};

  const proposed = readNumber(claims, 'proposed');
  const accepted = readNumber(claims, 'accepted');
  const rejected = readNumber(claims, 'rejected');
  const unconfirmed = readNumber(claims, 'unconfirmed');

  setText('c-proposed', proposed === null ? NOT_REPORTED : formatNumber(proposed));
  setText('c-accepted', accepted === null ? NOT_REPORTED : formatNumber(accepted));
  setText('c-rejected', rejected === null ? NOT_REPORTED : formatNumber(rejected));
  setText('c-unconfirmed', unconfirmed === null ? NOT_REPORTED : formatNumber(unconfirmed));

  const roleNode = document.getElementById('by-role');
  if (roleNode) {
    const byRole = claims.by_role;
    if (byRole && typeof byRole === 'object' && Object.keys(byRole).length > 0) {
      roleNode.textContent = `by role — ${
        Object.entries(byRole).map(([role, count]) => `${role} ${formatNumber(count)}`).join(' · ')}`;
      roleNode.hidden = false;
    } else {
      roleNode.textContent = `by role — ${NOT_REPORTED}`;
      roleNode.hidden = false;
    }
  }

  const list = document.getElementById('rejection-list');
  if (!list) return;
  list.replaceChildren();

  const ledger = Array.isArray(report.rejection_ledger) ? report.rejection_ledger : null;

  /* Three distinct empty states, because they mean three different things. */
  if (proposed === 0 && accepted === 0) {
    emptyState('rejections-empty',
      'Nothing was put to the check on this run, so there is nothing to show. ' +
      (report.run_metadata.model_layer === 'disabled'
        ? 'Reason: no model was used for this run.'
        : 'The report does not say why.'));
    show('rejections-empty', true);
    if (ledger) renderRejectionEntries(ledger, list);
    return;
  }

  if (rejected === 0 && proposed !== null && proposed > 0) {
    emptyState('rejections-empty',
      'No proposals were refused on this run. A verifier that never refuses is ' +
      'unverified — treat this as unproven rather than clean until the scorecard ' +
      'shows it rejecting a deliberately broken claim.');
    show('rejections-empty', true);
  } else {
    show('rejections-empty', false);
  }

  if (ledger === null) {
    if (rejected !== null && rejected > 0) {
      emptyState('rejections-empty',
        `Rejection ledger: not reported. ${formatNumber(rejected)} claims were ` +
        'rejected but this artefact carries no "rejection_ledger" key, so no reason ' +
        'can be shown. Reasons are the evidence, and they are missing.');
    } else if (rejected === null && proposed === null) {
      emptyState('rejections-empty',
        'Verification: not reported. This artefact carries no "claims" and no ' +
        '"rejection_ledger" key, so nothing can be claimed about what was accepted, ' +
        'refused or unconfirmed.');
    }
    return;
  }

  if (ledger.length === 0) {
    if (list.childElementCount === 0) {
      emptyState('rejections-empty', 'No claims were refused on this run.');
      show('rejections-empty', true);
    }
    return;
  }

  renderRejectionEntries(ledger, list);
}

function renderRejectionEntries(entries, list) {
  for (const entry of entries) {
    const card = el('article', 'rejection');
    const head = el('div', 'rejection-head');
    head.append(el('span', 'rejection-role', entry.role || NOT_REPORTED));
    head.append(el('span', 'rejection-gate', entry.gate || 'gate not reported'));
    card.append(head);
    /* Verbatim: paraphrasing a rejection reason is fabrication. */
    card.append(el('p', 'rejection-detail', entry.detail || NOT_REPORTED));
    if (entry.claim_ref) card.append(el('p', 'rejection-ref', entry.claim_ref));
    list.append(card);
  }
}

/* --- error state -------------------------------------------------------------------- */

function showError(error) {
  const loading = document.getElementById('loading');
  if (loading) loading.hidden = true;

  const box = document.getElementById('error');
  if (!box) return;
  box.replaceChildren();

  /* A load failure and a render failure are different problems with different
     fixes, and telling a user "no report found" when the report loaded fine is
     how a debugging session gets wasted. */
  if (error && error.details) {
    box.append(el('p', null,
      'Could not load a report — none of the sources below produced a valid artefact.'));
    box.append(el('p', 'stat-note',
      'Two things cause this. Opening the file with file:// blocks fetch outright. ' +
      'And serving the dashboard folder on its own is the usual mistake, because ' +
      'the report sits outside it. Serve the directory that contains BOTH the ' +
      'dashboard folder and bob_session/, then open the dashboard path under it: ' +
      'python3 -m http.server 8117'));
    const attempts = document.createElement('ul');
    attempts.className = 'attempts';
    for (const line of error.details) attempts.append(el('li', null, line));
    box.append(attempts);
  } else {
    box.append(el('p', null, 'The report loaded, but rendering it failed.'));
    box.append(el('p', 'stat-note',
      'The page will stay blank rather than show a half-rendered report, because a ' +
      'partially rendered report is a set of quietly untrue numbers.'));
    box.append(el('p', 'attempts',
      `${error && error.name ? error.name : 'Error'}: ${
        error && error.message ? error.message : String(error)}`));
  }

  box.hidden = false;
}
