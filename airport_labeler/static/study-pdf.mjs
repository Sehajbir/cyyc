// Local PDF.js avoids mobile browsers' non-scrollable native PDF embeds.
import { getDocument, GlobalWorkerOptions } from './vendor/pdfjs/pdf.min.mjs';
GlobalWorkerOptions.workerSrc = '/static/vendor/pdfjs/pdf.worker.min.mjs';
const file = new URLSearchParams(location.search).get('file');
const host = document.getElementById('pages');
const status = document.getElementById('status');
const slots = [];
let pdf;
let observer;
let jumping = false;
let jumpTimer;
let scrollTimer;
let pendingPage = Number(location.hash.match(/page=(\d+)/)?.[1]) || 1;

async function render(slot) {
  if (slot.busy || slot.canvas || !slot.near) return;
  slot.busy = true;
  try {
    const page = await pdf.getPage(slot.number);
    const width = slot.element.clientWidth;
    const scale = width / page.getViewport({ scale: 1 }).width;
    // Bound bitmap memory on high-density phones.
    const ratio = Math.min(devicePixelRatio || 1, 2);
    const viewport = page.getViewport({ scale: scale * ratio });
    const canvas = document.createElement('canvas');
    canvas.width = Math.floor(viewport.width);
    canvas.height = Math.floor(viewport.height);
    await page.render({ canvasContext: canvas.getContext('2d'), viewport }).promise;
    if (slot.near && width === slot.element.clientWidth) {
      slot.element.append(canvas);
      slot.canvas = canvas;
    } else {
      canvas.width = canvas.height = 0;
    }
    page.cleanup();
  } catch (error) {
    slot.element.querySelector('span').textContent = `Page ${slot.number} could not load. Use Open PDF to read it.`;
  } finally {
    slot.busy = false;
  }
}
function release(slot) {
  if (!slot.canvas) return;
  slot.canvas.remove();
  slot.canvas.width = slot.canvas.height = 0;
  slot.canvas = null;
}
function jump(number) {
  pendingPage = Math.max(1, Math.min(pdf?.numPages || Infinity, number));
  const slot = slots[pendingPage - 1];
  if (!slot) return;
  jumping = true;
  slot.element.scrollIntoView({ block: 'start' });
  clearTimeout(jumpTimer);
  jumpTimer = setTimeout(() => { jumping = false; }, 250);
}
window.addEventListener('hashchange', () => jump(Number(location.hash.match(/page=(\d+)/)?.[1]) || 1));
window.addEventListener('message', (event) => {
  if (event.origin === location.origin && event.source === parent && event.data?.type === 'study-jump' && Number.isInteger(event.data.page)) jump(event.data.page);
});
window.addEventListener('scroll', () => {
  clearTimeout(scrollTimer);
  scrollTimer = setTimeout(() => {
    if (jumping || !slots.length) return;
    const slot = slots.find(s => s.element.getBoundingClientRect().bottom > innerHeight * .25);
    if (slot) parent.postMessage({ type: 'study-page', page: slot.number, file }, location.origin);
  }, 150);
}, { passive: true });
let resizeTimer;
window.addEventListener('resize', () => {
  clearTimeout(resizeTimer);
  resizeTimer = setTimeout(() => {
    slots.forEach(slot => { release(slot); if (slot.near) render(slot); });
  }, 200);
});
try {
  const url = new URL(file, location.origin);
  if (!file || url.origin !== location.origin || !/^\/api\/lessons\/[^/]+\/pdf$/.test(url.pathname)) throw new Error('Invalid lesson URL');
  pdf = await getDocument({ url: url.href, isEvalSupported: false }).promise;
  // Establish real page dimensions before jumping, so mixed-size PDFs stay aligned.
  for (let number = 1; number <= pdf.numPages; number++) {
    const page = await pdf.getPage(number);
    const viewport = page.getViewport({ scale: 1 });
    const element = document.createElement('section');
    element.className = 'page';
    element.style.aspectRatio = `${viewport.width} / ${viewport.height}`;
    element.setAttribute('aria-label', `Page ${number}`);
    const label = document.createElement('span');
    label.textContent = `Page ${number}`;
    element.append(label);
    host.append(element);
    slots.push({ element, number, near: false, busy: false, canvas: null });
  }
  status.hidden = true;
  observer = new IntersectionObserver(entries => {
    for (const entry of entries) {
      const slot = slots[Number(entry.target.dataset.index)];
      slot.near = entry.isIntersecting;
      if (slot.near) render(slot); else release(slot);
    }
  }, { rootMargin: '600px 0px' });
  slots.forEach((slot, index) => { slot.element.dataset.index = index; observer.observe(slot.element); });
  jump(pendingPage);
} catch (error) {
  status.textContent = 'Unable to display this PDF. Use the Open PDF link above to read it in your browser.';
}
