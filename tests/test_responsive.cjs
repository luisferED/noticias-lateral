// Real Chromium layout checks; no server, internet, or NDI runtime required.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const { pathToFileURL } = require('node:url');
const { spawnSync } = require('node:child_process');

const browser = process.env.CHROME_PATH || [
  'C:/Program Files/Google/Chrome/Application/chrome.exe',
  'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe',
].find(file => fs.existsSync(file));
assert(browser, 'Set CHROME_PATH to a Chromium executable');
const directory = fs.mkdtempSync(path.join(os.tmpdir(), 'noticias-responsive-'));
const html = fs.readFileSync(path.join(__dirname, '..', 'index.html'), 'utf8');
const fixture = html.replace('<script>', `<script>
  window.fetch = async url => ({ok: true, json: async () =>
    url === '/api/config' ? {rotate_seconds:15, refresh_seconds:180} : {items:[]}});
</script><script>`);
const check = `
  const frame = document.querySelector('iframe');
  const results = [];
  const near = (a,b) => Math.abs(a-b) < 0.02;
  async function check(width,height) {
    frame.style.width = width+'px'; frame.style.height = height+'px';
    // Flush layout and deliver resize explicitly: headless virtual time may
    // advance timers before the compositor delivers native iframe events.
    frame.getBoundingClientRect();
    frame.contentWindow.dispatchEvent(new frame.contentWindow.Event('resize'));
    await new Promise(resolve => setTimeout(resolve,100));
    const doc = frame.contentDocument;
    const canvas = doc.querySelector('.canvas');
    const rail = doc.querySelector('.news-rail');
    const rect = rail.getBoundingClientRect();
    const stage = canvas.getBoundingClientRect();
    const scale = Math.min(width/1920,height/1080);
    const css = frame.contentWindow.getComputedStyle;
    const ok = near(stage.width,1920*scale) && near(stage.height,1080*scale)
      && near(rect.x,1556*scale) && near(rect.y,78*scale)
      && near(rect.width,335*scale) && near(rect.height,747*scale)
      && rect.right <= width && rect.bottom <= height
      && canvas.offsetWidth === 1920 && canvas.offsetHeight === 1080
      && rail.offsetLeft === 1556
      && css(doc.body).backgroundColor === 'rgba(0, 0, 0, 0)'
      && css(canvas).backgroundColor === 'rgba(0, 0, 0, 0)';
    results.push({width,height,scale,x:rect.x,right:rect.right,ok});
  }
  frame.onload = async () => {
    // Reuse one frame to exercise actual window resize events.
    for (const size of [[1366,768],[1600,900],[1920,1080],[768,1366],[2560,1440]])
      await check(...size);
    document.querySelector('pre').textContent = JSON.stringify(results);
  };
  frame.srcdoc = ${JSON.stringify(fixture)};
`;
const testFile = path.join(directory, 'layout.html');
fs.writeFileSync(testFile, '<iframe style="border:0"></iframe><pre></pre><script>'
  + check.replace(/<\/script/gi, '<\\/script') + '</script>');
const run = spawnSync(browser, ['--headless', '--disable-gpu', '--no-first-run',
  '--no-default-browser-check', '--user-data-dir='+path.join(directory,'profile'),
  '--virtual-time-budget=5000', '--dump-dom', pathToFileURL(testFile).href],
  {encoding:'utf8', timeout:30000, maxBuffer:4*1024*1024});
assert.ifError(run.error);
assert.equal(run.status, 0, run.stderr);
const output = run.stdout.match(/<pre>([\s\S]*?)<\/pre>/);
assert(output && output[1], 'Browser did not complete layout checks: '+run.stderr);
const results = JSON.parse(output[1]);
assert.equal(results.length,5);
for (const result of results) {
  assert(result.ok, JSON.stringify(result));
  console.log('OK Chromium:',JSON.stringify(result));
}
