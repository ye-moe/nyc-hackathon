// Shelter Match: eligibility filtering over NYC shelters with public addresses, and the Intake Ready Packet.
(() => {
  const { esc } = HW;
  const $ = id => document.getElementById(id);
  const tel = p => { const d = String(p || '').replace(/\D/g, ''); return d.length >= 7 ? d.slice(0, 11) : ''; };
  const POP = { mental_health: 'Mental health', substance_use: 'Substance use', veterans: 'Veterans', seniors: 'Seniors',
                employment: 'Working', lgbtq: 'LGBTQ+', hiv: 'HIV/AIDS', medical: 'Medical', young_adults: 'Young adults' };
  let current = null, rows = [], profile = null;
  const showTab = HW.tabs('sm', drawMap);

  function card(o) {
    const d = o.details || {};
    const list = xs => xs && xs.length ? `<ul>${xs.map(x => `<li>${esc(x)}</li>`).join('')}</ul>` : '<p style="margin:0;color:var(--muted)">Not listed by the source.</p>';
    const tags = [o.walk_in ? '<span class="chip"><i class="mk mk-ring"></i>Walk-in / call</span>' : '<span class="chip"><i class="mk mk-solid"></i>City shelter</span>',
                  o.serves ? `<span class="chip">${esc(o.serves)}</span>` : '', ...o.populations.map(p => `<span class="chip">${esc(POP[p] || p)}</span>`),
                  d.confirm ? '<span class="chip">Call to confirm</span>' : ''].join('');
    const links = (d.links || []).map(l => `<a class="btn btn-ghost btn-sm" href="${esc(l.url)}" target="_blank" rel="noopener">${esc(l.label)}</a>`).join('');
    const where = encodeURIComponent([o.address, o.borough, 'NY'].filter(Boolean).join(', '));
    return `<details class="card" id="item-${esc(o.id)}"><summary>
        <span class="t">${esc(o.name)}</span><span class="more">Details</span>
        <span class="s">${esc([o.address, o.borough].filter(Boolean).join(', '))} · ${esc(o.why)}</span><span class="tags">${tags}</span>
      </summary><div class="body">
        <h5>How to get in</h5><p style="margin:0">${esc(d.how_to_get_in || o.access)}</p>
        <h5>Eligibility</h5>${list(d.eligibility)}
        <h5>What to bring</h5>${list(d.what_to_bring)}
        <h5>Contact</h5><p style="margin:0">${[o.phone, o.provider ? 'Run by ' + o.provider : ''].filter(Boolean).map(esc).join(' · ') || 'Not listed'}</p>
        ${d.confirm ? `<div class="banner" style="margin:12px 0 0">${esc(d.confirm)}</div>` : ''}
        ${d.caveats ? `<p style="color:var(--muted);font-size:13.5px">Research note: ${esc(d.caveats)}</p>` : ''}
        ${d.source_quote ? `<h5>Source${d.source_date ? ' (' + esc(d.source_date) + ')' : ''}</h5><p class="quote" style="margin:0">“${esc(d.source_quote.slice(0, 300))}${d.source_quote.length > 300 ? '…' : ''}”</p>` : ''}
        <div class="row">${tel(o.phone) ? `<a class="btn btn-light btn-sm" href="tel:${tel(o.phone)}">Call</a>` : ''}<a class="btn btn-dark btn-sm" target="_blank" rel="noopener" href="https://www.google.com/maps/dir/?api=1&travelmode=transit&destination=${where}">Directions</a>${o.source_url ? `<a class="btn btn-ghost btn-sm" href="${esc(o.source_url)}" target="_blank" rel="noopener">Source</a>` : ''}${links}
          <label class="btn btn-ghost btn-sm" style="cursor:pointer"><input type="checkbox" data-pick="${esc(o.id)}" style="margin:0 6px 0 0"> Add to packet</label></div>
      </div></details>`;
  }

  // Filters only narrow the eligible list; they never add shelters the person isn't eligible for.
  function applyFilters() {
    if (!current) return;
    const boro = $('x1').value, type = $('x2').value, sort = $('x3').value;
    rows = current.shelters.filter(s => (!boro || s.borough === boro) && (!type || (type === '__walk' ? s.walk_in : s.facility_type === type)));
    const by = { boro: (a, b) => (a.borough || '').localeCompare(b.borough || ''), beds: (a, b) => (b.beds || 0) - (a.beds || 0),
                 name: (a, b) => a.name.localeCompare(b.name) };
    if (by[sort]) rows = [...rows].sort(by[sort]);
    const picked = new Set([...document.querySelectorAll('[data-pick]:checked')].map(x => x.dataset.pick));
    $('counts').innerHTML = `<span class="chip">${current.total} eligible</span>${rows.length !== current.total ? `<span class="chip">${rows.length} shown</span>` : ''}
      <span class="chip"><i class="mk mk-solid"></i>City (DHS) shelter</span><span class="chip"><i class="mk mk-ring"></i>Walk-in / call</span>`;
    $('list').innerHTML = rows.map(card).join('') || '<div class="banner">No listed shelter matches. Clear a filter, or use the intake step above.</div>';
    document.querySelectorAll('[data-pick]').forEach(x => { x.checked = picked.has(x.dataset.pick); });
    if (!document.querySelector('[data-panel-for="sm"][data-view="map"]').hidden) drawMap();
  }
  ['x1', 'x2', 'x3'].forEach(id => $(id).addEventListener('change', applyFilters));

  function drawMap() {
    HW.map($('map'), rows.map(s => ({ id: s.id, lat: s.lat, lng: s.lng, title: s.name, kind: s.walk_in ? 'ring' : 'solid',
      subtitle: ` ${s.address}. ${s.serves}.${s.walk_in ? ' Walk-in / call.' : ''}` })), id => HW.reveal(showTab, id));
  }

  function render(r) {
    current = r;
    $('how').innerHTML = `<div class="banner"><b>How to get in:</b> ${esc(r.how_to_get_in)}</div>`;
    const opts = (xs, first) => first + [...new Set(xs.filter(Boolean))].sort().map(x => `<option>${esc(x)}</option>`).join('');
    $('x1').innerHTML = opts(r.shelters.map(s => s.borough), '<option value="">All</option>');
    $('x2').innerHTML = opts(r.shelters.map(s => s.facility_type), '<option value="">All</option><option value="__walk">Walk-in / call only</option>');
    $('notEligible').innerHTML = r.not_eligible.length ? `<details class="card"><summary><span class="t">Not eligible (${r.not_eligible.length}) and why</span><span class="more">Show</span>
        <span class="s">Shown so nothing is missed. Reasons come from each shelter's rules.</span></summary>
        <div class="body"><ul>${r.not_eligible.map(e => `<li><b>${esc(e.name)}</b>${e.address ? ` (${esc(e.address)})` : ''}: ${esc(e.reason)}</li>`).join('')}</ul></div></details>` : '';
    $('note').textContent = r.note || '';
    $('results').hidden = false;
    applyFilters();
  }

  $('form').addEventListener('submit', async e => {
    e.preventDefault();
    const f = new FormData(e.target);
    const body = { household: f.get('h'), gender: $('g').value, needs: f.getAll('need') };
    if ($('a').value) body.age = +$('a').value;
    if ($('bo').value) body.borough = $('bo').value;
    for (const k of ['fleeing_violence', 'in_dhs_shelter_last_12_months', 'veteran', 'lgbtq', 'employed']) body[k] = f.get(k) === 'on';
    profile = body;
    $('how').innerHTML = '<div class="banner">Matching…</div>';
    try { render(await HW.post('/shelters/match', body)); $('match').scrollIntoView({ behavior: 'smooth', block: 'start' }); }
    catch (err) { HW.offline($('how')); $('how').insertAdjacentHTML('beforeend', '<p style="color:var(--muted)">For shelter directions right now, call 311.</p>'); }
  });

  // ---- Intake Ready Packet ----
  const status = t => { $('packetStatus').textContent = t; };
  async function packet() {
    if (!profile) { status('Find shelters first, so the packet fits this person.'); $('match').scrollIntoView({ behavior: 'smooth' }); return null; }
    status('Building…');
    const body = { ...profile, shelter_ids: [...document.querySelectorAll('[data-pick]:checked')].map(x => x.dataset.pick) };
    if (!body.shelter_ids.length) delete body.shelter_ids;
    if ($('lang').value) body.client_language = $('lang').value;
    try { const k = await HW.post('/shelters/intake-packet', body); preview(k); status(''); return k; }
    catch (e) { status(e.message === 'Failed to fetch' ? `Can't reach the API at ${HW.API}.` : 'Couldn\'t build the packet: ' + e.message); return null; }
  }
  function preview(k) {
    const ul = xs => `<ul style="margin:0;padding-left:18px;color:#C9CBD0;font-size:14.5px">${xs.map(x => `<li>${esc(x)}</li>`).join('')}</ul>`;
    const doors = k.go_to.map(d => `<tr><td><b>${esc(d.name)}</b><br><span style="color:var(--muted)">${esc([d.address, d.transit].filter(Boolean).join(' · '))}</span></td><td>${esc(d.hours || '')}</td></tr>`).join('');
    $('packetOut').innerHTML = `<div class="panel"><h3>Your next step</h3><div class="banner" style="margin:0 0 14px"><b>${esc(k.first_step)}</b></div>
        ${doors ? `<div class="table-scroll"><table><tbody>${doors}</tbody></table></div>` : ''}
        <h3 style="margin-top:22px">What to bring</h3>${ul(k.bring)}</div>
      <div class="panel"><h3>Text message · review before sending</h3><p style="margin:0;font-size:14px;color:#C9CBD0;white-space:pre-line">${esc(k.text)}</p>
        <h3 style="margin-top:22px">If you're denied</h3>${ul(k.if_denied)}</div>`;
    $('packetOut').hidden = false;
  }
  $('packetBtn').onclick = async () => { const k = await packet(); if (k) HW.openHtml(k.html); };
  $('smsBtn').onclick = async () => { const k = await packet(); if (k) { await navigator.clipboard.writeText(k.text); status('Text message copied. Review it before sending.'); } };
})();
