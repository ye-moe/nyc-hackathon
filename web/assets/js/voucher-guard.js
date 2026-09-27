// Voucher Guard: scraped listings flagged for source-of-income discrimination, plus a paste-a-listing check.
(() => {
  const { esc, usd } = HW;
  const LABEL = { violation: 'Discriminatory', needs_review: 'Questionable', no_issue_found: 'No issue found' };
  const MK = { violation: 'mk-solid', needs_review: 'mk-ring', no_issue_found: 'mk-dash' };
  const PIN = { violation: 'solid', needs_review: 'ring', no_issue_found: 'muted' };
  const RULE = { R1: 'Refuses vouchers', R2: 'Income rule on full rent', R3: 'Job or credit screening' };
  const $ = id => document.getElementById(id);
  let items = [];
  const details = {};
  document.getElementById('scanLink').href = HW.API + '/voucher-guard/scan/';
  const showTab = HW.tabs('vg', drawMap);

  function highlight(text, flags) {
    const spans = flags.filter(f => f.span).map(f => f.span).sort((a, b) => a[0] - b[0]);
    let out = '', i = 0;
    for (const [s, e] of spans) { if (s < i) continue; out += esc(text.slice(i, s)) + '<mark>' + esc(text.slice(s, e)) + '</mark>'; i = e; }
    return out + esc(text.slice(i));
  }

  // The analysis body shared by flagged listings and the paste-a-listing check.
  function analysis(result, ctx) {
    const probs = result.flags.filter(f => f.severity !== 'info');
    const calc = probs.find(f => f.calculation);
    return `<h5>What we found</h5><ul>${probs.map(f => `<li><b>“${esc(f.evidence_text)}”</b>: ${esc(f.explanation)}</li>`).join('') || '<li>Nothing that excludes voucher holders.</li>'}</ul>
      ${calc ? `<h5>The math</h5><ol>${calc.calculation.steps.map(s => `<li>${esc(s)}</li>`).join('')}</ol>` : ''}
      <h5>Listing as checked</h5><p class="quote">${highlight(result.analyzed_text, result.flags)}</p>
      ${result.verdict !== 'no_issue_found' ? `<div class="row"><button class="btn btn-light btn-sm" data-act="packet" data-id="${esc(ctx)}" type="button">Evidence packet</button><button class="btn btn-dark btn-sm" data-act="complaint" data-id="${esc(ctx)}" type="button">Draft CHR complaint</button></div>` : ''}`;
  }

  function card(x) {
    const clause = x.flags[0] ? `“${x.flags[0].clause}”` : x.text.slice(0, 90);
    const meta = [x.bedrooms != null ? (x.bedrooms === 0 ? 'Studio' : x.bedrooms + 'BR') : '', x.rent ? usd(x.rent) + '/mo' : '',
                  [x.address, x.borough].filter(Boolean).join(', ') || 'Location not stated', x.source, x.discovered_at ? 'found ' + x.discovered_at.slice(0, 10) : '']
                 .filter(Boolean).join(' · ');
    const rules = [...new Set(x.flags.map(f => f.rule))].map(r => `<span class="chip">${esc(RULE[r] || r)}</span>`).join('');
    return `<details class="card" id="item-${esc(x.id)}" data-id="${esc(x.id)}"><summary>
        <span class="t">${esc(clause)}</span><span class="more">Details</span>
        <span class="s">${esc(meta)}</span>
        <span class="tags"><span class="chip"><i class="mk ${MK[x.verdict]}"></i>${LABEL[x.verdict]}</span>${rules}</span>
      </summary><div class="body" data-body><p>Loading…</p></div></details>`;
  }

  async function openCard(el) {
    const id = el.dataset.id;
    if (!details[id]) details[id] = await HW.get('/guard/listings/' + encodeURIComponent(id));
    const d = details[id];
    el.querySelector('[data-body]').innerHTML = analysis(d.result, id)
      + (d.url ? `<div class="row"><a class="btn btn-ghost btn-sm" href="${esc(d.url)}" target="_blank" rel="noopener">Original listing</a></div>` : '');
  }
  $('list').addEventListener('toggle', e => { if (e.target.open && e.target.dataset.id) openCard(e.target); }, true);

  async function load() {
    const q = new URLSearchParams({ verdict: $('f1').value });
    if ($('f2').value) q.set('borough', $('f2').value);
    if ($('f3').value) q.set('rule', $('f3').value);
    try {
      const g = await HW.get('/guard/listings?' + q);
      items = g.items;
      const pct = g.total_scanned ? Math.round(100 * (g.counts.violation + g.counts.needs_review) / g.total_scanned) : 0;
      $('counts').innerHTML = `<span class="chip">${g.total_scanned.toLocaleString()} scanned</span>
        <span class="chip"><i class="mk mk-solid"></i>${g.counts.violation} discriminatory</span>
        <span class="chip"><i class="mk mk-ring"></i>${g.counts.needs_review} questionable</span><span class="chip">${pct}% flagged</span>`;
      $('list').innerHTML = items.map(card).join('') || '<div class="banner">No listings match. Scraped listings appear here once the scraper runs.</div>';
      if (!document.querySelector('[data-panel-for="vg"][data-view="map"]').hidden) drawMap();
    } catch (e) { HW.offline($('list')); $('counts').innerHTML = ''; }
  }
  function drawMap() {
    HW.map($('map'), items.map(x => ({ id: x.id, lat: x.lat, lng: x.lng, kind: PIN[x.verdict],
      title: x.flags[0] ? `“${x.flags[0].clause}”` : x.text.slice(0, 60),
      subtitle: ` ${LABEL[x.verdict]}. ${[x.address, x.rent ? usd(x.rent) + '/mo' : ''].filter(Boolean).join(' · ')}` })),
      id => { HW.reveal(showTab, id); const el = $('item-' + id); if (el) openCard(el); });
  }
  ['f1', 'f2', 'f3'].forEach(id => $(id).addEventListener('change', load));

  // ---- paste a listing ----
  let checked = null;
  $('check').addEventListener('submit', async e => {
    e.preventDefault();
    const text = $('t').value.trim(), out = $('checkResult');
    if (!text) { out.innerHTML = '<p style="color:var(--muted);margin:0">Paste some listing text first.</p>'; return; }
    out.innerHTML = '<p style="color:var(--muted);margin:0">Checking…</p>';
    try {
      checked = await HW.post('/analyze', { text });
      out.innerHTML = `<span class="chip"><i class="mk ${MK[checked.verdict]}"></i>${LABEL[checked.verdict]}</span>
        <div class="card" style="margin-top:10px"><div class="body" style="border-top:0">${analysis(checked, 'check')}</div></div>`;
    } catch (err) { HW.offline(out); }
  });

  // ---- deliverables ----
  document.addEventListener('click', async e => {
    const b = e.target.closest('button[data-act]'); if (!b) return;
    const id = b.dataset.id;
    const result = id === 'check' ? checked : details[id].result;
    const listing = id === 'check' ? { source: 'Pasted text' } : { url: details[id].url, source: details[id].source, seen_on: details[id].discovered_at };
    try {
      if (b.dataset.act === 'packet') HW.openHtml((await HW.post('/packet', { result, listing_url: listing.url })).html);
      else HW.openHtml(await HW.post('/complaint/html', await HW.post('/complaint', { result, listing, reporter: { role: 'caseworker' } }), 'text'));
    } catch (err) { alert('Couldn\'t build it: ' + err.message); }
  });

  load();
})();
