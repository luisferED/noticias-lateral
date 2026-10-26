const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

async function main() {
  const html = fs.readFileSync(path.join(__dirname, '..', 'index.html'), 'utf8');
  const script = html.match(/<script>([\s\S]*?)<\/script>/)[1];
  const elements = new Map();
  function element(id) {
    if (!elements.has(id)) elements.set(id, {
      style: { setProperty() {} }, classList: { add() {}, remove() {} },
      removeAttribute() {}, textContent: '', scrollHeight: 100,
      scrollWidth: 200, clientWidth: 250,
    });
    return elements.get(id);
  }
  const timers = new Map();
  const items = Array.from({ length: 14 }, (_, i) => ({
    title: `Noticia ${i}`, url: `https://eldeber.com.bo/pais/${i}`,
    image: `https://pxcdn.eldeber.com.bo/${i}.jpg`, section: 'PAIS',
  }));
  const context = vm.createContext({
    console,
    document: { getElementById: element, querySelector: element,
      fonts: { ready: Promise.resolve() } },
    window: { setTimeout(fn) { fn(); }, setInterval(fn, ms) { timers.set(ms, fn); } },
    fetch: async (url) => ({ ok: true, json: async () => url === '/api/config'
      ? { rotate_seconds: 15, refresh_seconds: 180 } : { items } }),
  });
  vm.runInContext(script, context);
  await new Promise(setImmediate);
  assert(timers.has(15000));
  assert(timers.has(180000));
  const title = element('storyTitle');
  const seen = new Set([title.textContent]);
  for (let i = 0; i < 12; i++) {
    timers.get(15000)();
    seen.add(title.textContent);
  }
  assert.equal(title.textContent, 'Noticia 12');
  await timers.get(180000)();
  assert.equal(title.textContent, 'Noticia 12', 'refresh must not interrupt or restart rotation');
  timers.get(15000)();
  seen.add(title.textContent);
  assert.equal(title.textContent, 'Noticia 13');
  assert.equal(seen.size, 14, 'all queued stories must appear');
  timers.get(15000)();
  assert.equal(title.textContent, 'Noticia 0');
  console.log('OK: 15s rotation, 180s refresh, full queue without reset');
}

main().catch((error) => { console.error(error); process.exitCode = 1; });
