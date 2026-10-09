// Run with: node --test airport_labeler/tests/study-pdf.test.mjs
import test from 'node:test';
import assert from 'node:assert/strict';
import vm from 'node:vm';
import { readFile } from 'node:fs/promises';
const source = (await readFile(new URL('../static/study-pdf.mjs', import.meta.url), 'utf8'))
  .replace(/^import .*;$/m, '');

test('compact reader loads pages, resumes, validates jumps and saves scroll position', async () => {
  const events = {};
  const messages = [];
  const pages = [];
  const timers = [];
  let jumped;
  const status = {};
  const parent = { postMessage: data => messages.push(data) };
  const element = () => ({
    style: {}, dataset: {}, children: [], setAttribute() {},
    append(child) { this.children.push(child); },
    scrollIntoView() { jumped = pages.indexOf(this) + 1; },
    getBoundingClientRect() { return { bottom: (pages.indexOf(this) - 1) * 500 }; },
  });
  const context = vm.createContext({
    URL, URLSearchParams, Number, Math, Infinity,
    location: { origin: 'https://study.test', search: '?file=%2Fapi%2Flessons%2Fabc%2Fpdf', hash: '#page=2' },
    parent, innerHeight: 600,
    window: { addEventListener: (name, handler) => { events[name] = handler; } },
    document: { getElementById: id => id === 'status' ? status : { append: page => pages.push(page) }, createElement: element },
    GlobalWorkerOptions: {},
    getDocument: () => ({ promise: Promise.resolve({ numPages: 3, getPage: async () => ({ getViewport: () => ({ width: 600, height: 800 }) }) }) }),
    IntersectionObserver: class { observe() {} },
    setTimeout: callback => { timers.push(callback); return timers.length; }, clearTimeout() {},
  });
  await vm.runInContext(`(async () => { ${source} })()`, context);
  assert.equal(pages.length, 3);
  assert.equal(status.hidden, true);
  assert.equal(jumped, 2);
  const message = { origin: 'https://study.test', source: parent, data: { type: 'study-jump', page: 3 } };
  events.message({ ...message, origin: 'https://other.test' });
  assert.equal(jumped, 2);
  events.message(message);
  assert.equal(jumped, 3);
  events.message({ ...message, data: { type: 'study-jump', page: 99 } });
  assert.equal(jumped, 3, 'out-of-range navigation is clamped');
  timers.splice(0).forEach(callback => callback());
  events.scroll();
  timers.splice(0).forEach(callback => callback());
  assert.equal(messages.at(-1).page, 3);
  assert.equal(messages.at(-1).file, '/api/lessons/abc/pdf');
});
