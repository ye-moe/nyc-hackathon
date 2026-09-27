// Open Doors: Housing Connect lotteries + voucher-friendly listings, and the Housing Plan deliverable.
(() => {
  const { esc, usd } = HW;
  const $ = id => document.getElementById(id);
  const bed = b => b === 0 ? 'Studio' : b + 'BR';
  const KIND = { lottery: ['mk-solid', 'Housing Connect lottery'], listing: ['mk-ring', 'Voucher-friendly listing'],
                 inventory: ['mk-dash', 'Historical rental record'] };
  let items = [];
  const showTab = HW.tabs('od', drawMap);

  function lotteryBody(i, hh) {
    const rows = i.unit_offers.map(u => {
      const inc = hh ? u.income_by_household_size[String(hh)] : null;
      const incTxt = inc ? `${usd(inc[0])}–${usd(inc[1])}` : Object.keys(u.income_by_household_size).length ? 'Varies by size' : '—';
      const covers = u.rent_within_voucher_limit == null ? '—' : u.rent_within_voucher_limit ? 'Yes' : 'No';
      return `<tr><td>${u.count} × ${esc(u.layout)}</td><td>${u.rent ? usd(u.rent) : 'Set by income'}</td><td>${u.household_min ?? '?'}–${u.household_max ?? '?'}</td><td>${incTxt}</td><td>${covers}</td></tr>`;
    }).join('');
    return `${rows ? `<h5>Units${hh ? ` (income for a household of ${esc(hh)})` : ''}</h5><div class="table-scroll"><table><thead><tr><th>Unit</th><th>Rent</th><th>Household</th><th>Income</th><th>Voucher covers rent</th></tr></thead><tbody>${rows}</tbody></table></div>` : ''}
      <h5>If you have a voucher</h5><p style="margin:0">${esc(i.voucher_status)}</p>
      <h5>How to apply</h5><p style="margin:0">Online on Housing Connect before the deadline${i.paper_application_address ? `, or by paper application to ${esc(i.paper_application_address)}` : ''}.</p>
      <div class="row"><a class="btn btn-light btn-sm" href="${esc(i.url)}" target="_blank" rel="noopener">Apply on Housing Connect</a>${dirBtn(i)}${pick(i)}</div>`;
  }
  function listingBody(i) {
    return `<p>${esc(i.voucher_status)}</p><p style="color:var(--muted);font-size:13.5px">Source: ${esc(i.source)}. Checked by Voucher Guard: nothing discriminatory found.</p>
      <div class="row">${i.url ? `<a class="btn btn-light btn-sm" href="${esc(i.url)}" target="_blank" rel="noopener">Open listing</a>` : ''}${dirBtn(i)}${pick(i)}</div>`;
  }
  function inventoryBody(i) {
    return `<p>Historical rental record${i.snapshot_month ? ` (${esc(i.snapshot_month)})` : ''}. Current availability and voucher acceptance have not been verified.</p>
      <p style="color:var(--muted);font-size:13.5px">Source: ${esc(i.source)}</p>${i.url ? `<div class="row"><a class="btn btn-ghost btn-sm" href="${esc(i.url)}" target="_blank" rel="noopener">Original source</a></div>` : ''}`;
  }
  const dirBtn = i => i.address ? `<a class="btn btn-dark btn-sm" target="_blank" rel="noopener" href="https://www.google.com/maps/dir/?api=1&travelmode=transit&destination=${encodeURIComponent([i.address, i.borough, 'NY'].filter(Boolean).join(', '))}">Directions</a>` : '';
  const pick = i => `<label class="btn btn-ghost btn-sm" style="cursor:pointer"><input type="checkbox" data-pick="${esc(i.id)}" style="margin:0 6px 0 0"> Add to plan</label>`;

  function card(i, hh) {
    const [mk, label] = KIND[i.kind] || KIND.listing;
    const sub = i.kind === 'lottery'
      ? [i.address, i.borough, i.neighborhood].filter(Boolean).join(' · ')
      : [i.bedrooms.map(bed).join('/'), i.rent ? usd(i.rent) + '/mo' : '', [i.address, i.borough].filter(Boolean).join(', '), i.source].filter(Boolean).join(' · ');
    const tags = [`<span class="chip"><i class="mk ${mk}"></i>${label}</span>`];
    if (i.deadline) tags.push(`<span class="chip">Apply by ${esc(i.deadline)}${i.days_left != null ? ` · ${i.days_left} day${i.days_left === 1 ? '' : 's'}` : ''}</span>`);
    if (i.kind === 'lottery') i.bedrooms.forEach(b => tags.push(`<span class="chip">${bed(b)}</span>`));
    if (i.units) tags.push(`<span class="chip">${i.units} units</span>`);
    if (i.kind === 'listing' && i.within_voucher_limit) tags.push('<span class="chip">Within voucher limit</span>');
    const body = i.kind === 'lottery' ? lotteryBody(i, hh) : i.kind === 'inventory' ? inventoryBody(i) : listingBody(i);
    return `<details class="card" id="item-${esc(i.id)}"><summary>
        <span class="t">${esc(i.title)}</span><span class="more">Details</span>
        <span class="s">${esc(sub || 'Location not stated')}</span><span class="tags">${tags.join('')}</span>
      </summary><div class="body">${body}</div></details>`;
  }

  function params() {
    const q = new URLSearchParams();
    if ($('hh').value) q.set('household_size', $('hh').value);
    if ($('inc').value) q.set('income', $('inc').value);
    if ($('b').value) q.set('bedrooms', $('b').value);
    if ($('bo').value) q.set('borough', $('bo').value);
    if ($('k').value) q.set('kind', $('k').value);
    q.set('has_voucher', $('voucher').checked);
    q.set('within_voucher_limit', $('limit').checked);
    return q;
  }

  let seq = 0;
  async function load() {
    const me = ++seq;
    try {
      const f = await HW.get('/vacancies?' + params());
      if (me !== seq) return;   // a newer filter change is already loading
      const picked = new Set([...document.querySelectorAll('[data-pick]:checked')].map(x => x.dataset.pick));
      items = f.items;
      const hidden = f.hidden.discriminatory + f.hidden.needs_review, hh = $('hh').value;
      $('counts').innerHTML = `<span class="chip"><i class="mk mk-solid"></i>${f.counts.lotteries} open lotteries</span>
        <span class="chip"><i class="mk mk-ring"></i>${f.counts.listings} voucher-friendly listings</span>
        ${hidden ? `<span class="chip">${hidden} hidden (${f.hidden.discriminatory} discriminatory, ${f.hidden.needs_review} questionable)</span>` : ''}`;
      const lotteries = items.filter(i => i.kind === 'lottery').length;
      const banner = hh || $('inc').value
        ? `<div class="banner"><b>${hh ? `A household of ${esc(hh)}` : 'This household'}${$('inc').value ? ` earning ${usd(+$('inc').value)}` : ''}</b> matches ${lotteries} open lotter${lotteries === 1 ? 'y' : 'ies'} and ${items.length - lotteries} listing${items.length - lotteries === 1 ? '' : 's'}${$('voucher').checked ? ', counting the voucher' : ''}.</div>` : '';
      $('list').innerHTML = banner + (items.map(i => card(i, hh)).join('') || '<div class="banner">Nothing matches these filters. Try removing one.</div>')
        + `<p style="color:var(--muted);font-size:13px;line-height:1.55">${f.notes.map(esc).join('<br>')}${f.lotteries_as_of ? `<br>Lotteries updated ${esc(f.lotteries_as_of)}.` : ''}</p>`;
      document.querySelectorAll('[data-pick]').forEach(x => { x.checked = picked.has(x.dataset.pick); });
      if (!document.querySelector('[data-panel-for="od"][data-view="map"]').hidden) drawMap();
    } catch (e) { if (me === seq) { HW.offline($('list')); $('counts').innerHTML = ''; } }
  }

  function drawMap() {
    const pts = [];
    for (const i of items) {
      const kind = i.kind === 'lottery' ? 'solid' : i.kind === 'listing' ? 'ring' : 'muted';
      const sub = i.kind === 'lottery' ? ` Lottery${i.deadline ? ', apply by ' + i.deadline : ''}.` : ` ${(KIND[i.kind] || KIND.listing)[1]}${i.rent ? ', ' + usd(i.rent) + '/mo' : ''}.`;
      if (i.buildings && i.buildings.length > 1)
        i.buildings.forEach(b => pts.push({ id: i.id, lat: b.lat, lng: b.lng, title: `${i.title} (${b.address || ''})`, subtitle: sub, kind }));
      else pts.push({ id: i.id, lat: i.lat, lng: i.lon ?? i.lng, title: i.title, subtitle: sub, kind });
    }
    HW.map($('map'), pts, id => HW.reveal(showTab, id));
  }

  $('feed').addEventListener('submit', e => e.preventDefault());
  $('feed').addEventListener('input', e => { if (e.target.dataset.pick) return; clearTimeout(load.t); load.t = setTimeout(load, 300); });

  // ---- Housing Plan ----
  function planBody() {
    const body = { has_voucher: $('voucher').checked,
                   item_ids: [...document.querySelectorAll('[data-pick]:checked')].map(x => x.dataset.pick) };
    if ($('hh').value) body.household_size = +$('hh').value;
    if ($('inc').value) body.income = +$('inc').value;
    if ($('b').value) body.bedrooms = +$('b').value;
    if ($('bo').value) body.borough = $('bo').value;
    if ($('lang').value) body.client_language = $('lang').value;
    if (!body.item_ids.length) delete body.item_ids;
    return body;
  }
  const status = t => { $('planStatus').textContent = t; };
  function preview(p) {
    const rows = p.lotteries.map(l => `<tr><td>${esc(l.title)}</td><td>${esc(l.deadline || '—')}${l.days_left != null ? ` · ${l.days_left} days` : ''}</td>
      <td>${l.units.map(u => `${u.count} × ${esc(u.layout)}${u.rent ? ' · ' + usd(u.rent) : ''}`).join('<br>') || '—'}</td><td>☐</td></tr>`).join('');
    const letter = p.listings[0];
    $('planOut').innerHTML = `<div class="panel"><h3>Apply by deadline</h3>
        ${rows ? `<div class="table-scroll"><table><thead><tr><th>Lottery</th><th>Deadline</th><th>Units that fit</th><th>Done</th></tr></thead><tbody>${rows}</tbody></table></div>` : '<p style="color:#C9CBD0">No open lottery fits this household right now.</p>'}
        <h3 style="margin-top:22px">Documents to gather</h3><ul style="margin:0;padding-left:18px;color:#C9CBD0;font-size:14.5px">${p.checklist.map(c => `<li>${esc(c)}</li>`).join('')}</ul></div>
      <div class="panel"><h3>Landlord letter · draft</h3>
        ${letter ? `<p style="margin:0 0 10px;font-size:14px;color:#C9CBD0;white-space:pre-line">${esc(letter.letter)}</p>
          <div style="display:flex;gap:8px;flex-wrap:wrap;margin-top:14px"><button class="btn btn-light btn-sm" type="button" id="copyLetter">Copy letter</button><button class="btn btn-dark btn-sm" type="button" id="openPlan">Open full plan</button></div>`
          : '<p style="color:#C9CBD0">No voucher-friendly listing in this plan, so no letter yet.</p><button class="btn btn-dark btn-sm" type="button" id="openPlan">Open full plan</button>'}</div>`;
    $('planOut').hidden = false;
    $('openPlan').onclick = () => HW.openHtml(p.html);
    if ($('copyLetter')) $('copyLetter').onclick = () => navigator.clipboard.writeText(letter.letter).then(() => status('Letter copied. Review it before sending.'));
  }
  async function run(fn) {
    status('Building…');
    try { await fn(); } catch (e) { status(e.message === 'Failed to fetch' ? `Can't reach the API at ${HW.API}.` : 'Couldn\'t build the plan: ' + e.message); }
  }
  $('planBtn').onclick = () => run(async () => { const p = await HW.post('/vacancies/plan', planBody()); preview(p); HW.openHtml(p.html); status(p.headline); });
  $('icsBtn').onclick = () => run(async () => { HW.download(await HW.post('/vacancies/plan.ics', planBody(), 'blob'), 'housing-deadlines.ics'); status('Calendar file downloaded.'); });
  $('smsBtn').onclick = () => run(async () => { const p = await HW.post('/vacancies/plan', planBody()); await navigator.clipboard.writeText(p.text); preview(p); status('Text message copied. Review it before sending.'); });

  load();
})();
