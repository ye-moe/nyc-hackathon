// Shared helpers for the Homeward pages. The API (core/api.py) serves these pages, so calls go to the same origin.
//   API base: ?api=… in the URL, else the page's own origin (http://localhost:8000 when opened as a file)

const HW = (() => {
  const API = new URLSearchParams(location.search).get('api')
    || (location.protocol === 'file:' ? 'http://localhost:8000' : location.origin);
  const esc = s => String(s ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[c]);
  const usd = n => n == null ? '' : '$' + Math.round(n).toLocaleString('en-US');

  async function get(path) {
    const r = await fetch(API + path);
    if (!r.ok) throw new Error(`${path} ${r.status}`);
    return r.json();
  }
  async function post(path, body, as = 'json') {
    const r = await fetch(API + path, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) });
    if (!r.ok) {
      let msg = r.status;
      try { msg = (await r.json()).detail || msg; } catch (e) { /* not JSON */ }
      throw new Error(msg);
    }
    return as === 'json' ? r.json() : as === 'text' ? r.text() : r.blob();
  }
  const openHtml = html => window.open(URL.createObjectURL(new Blob([html], { type: 'text/html' })), '_blank');
  const download = (blob, name) => { const a = document.createElement('a'); a.href = URL.createObjectURL(blob); a.download = name; a.click(); };
  const offline = el => { el.innerHTML = `<div class="banner">Can't reach the Homeward API at ${esc(API)}. Start it with <b>python3 -m uvicorn core.api:app --port 8000</b>.</div>`; };

  // List / Map toggle: <div class="toggle" data-toggle="x"> + panels [data-panel-for="x"][data-view="list|map"]
  function tabs(name, onMap) {
    const group = document.querySelector(`[data-toggle="${name}"]`);
    const buttons = group.querySelectorAll('button[data-view]');
    const show = view => {
      buttons.forEach(b => b.setAttribute('aria-selected', String(b.dataset.view === view)));
      document.querySelectorAll(`[data-panel-for="${name}"]`).forEach(p => { p.hidden = p.dataset.view !== view; });
      if (view === 'map' && onMap) onMap();
    };
    buttons.forEach(b => b.addEventListener('click', () => show(b.dataset.view)));
    return show;
  }

  // ---------- Google Maps (Maps JavaScript API; key from GET /config) ----------
  let mapsPromise = null;
  function loadMaps() {
    if (mapsPromise) return mapsPromise;
    mapsPromise = get('/config').then(cfg => new Promise((resolve, reject) => {
      if (!cfg.google_maps_api_key) return reject(new Error('no-key'));
      window.__hwMaps = () => resolve(window.google.maps);
      const s = document.createElement('script');
      s.src = `https://maps.googleapis.com/maps/api/js?key=${encodeURIComponent(cfg.google_maps_api_key)}&v=weekly&libraries=marker&loading=async&callback=__hwMaps`;
      s.async = true; s.onerror = () => reject(new Error('load-failed'));
      document.head.appendChild(s);
    }));
    return mapsPromise;
  }
  // Pins differ by shape/contrast, never hue: solid (paper), ring (dark + paper border), muted (gray).
  const PIN = { solid: ['#EEEDEA', '#141619', '#141619'], ring: ['#141619', '#EEEDEA', '#EEEDEA'], muted: ['#6D7178', '#EEEDEA', '#EEEDEA'] };

  // points: [{id, lat, lng, title, subtitle, kind: 'solid'|'ring'|'muted'}]
  async function map(el, points, onDetails) {
    const pts = points.filter(p => p.lat != null && p.lng != null);
    const note = el.parentElement.parentElement.querySelector('.map-note');
    if (note) note.textContent = points.length > pts.length
      ? `${pts.length} on the map. ${points.length - pts.length} without an address are in the list only.` : `${pts.length} on the map.`;
    let maps;
    try { maps = await loadMaps(); }
    catch (e) {
      el.innerHTML = `<div style="padding:18px;color:var(--muted);font-size:14px">${e.message === 'no-key'
        ? 'The map needs GOOGLE_MAPS_API_KEY in .env (then restart the API).' : 'Couldn\'t load Google Maps.'}</div>`;
      return;
    }
    el.style.filter = 'grayscale(1)';   // match the grayscale theme
    const m = new maps.Map(el, { center: { lat: 40.7128, lng: -73.97 }, zoom: 11, mapId: 'DEMO_MAP_ID', colorScheme: 'DARK',
      streetViewControl: false, mapTypeControl: false });
    const info = new maps.InfoWindow();
    const bounds = new maps.LatLngBounds();
    for (const p of pts) {
      const [bg, border, glyph] = PIN[p.kind] || PIN.solid;
      const pin = new maps.marker.PinElement({ background: bg, borderColor: border, glyphColor: glyph });
      const mk = new maps.marker.AdvancedMarkerElement({ map: m, position: { lat: p.lat, lng: p.lng }, title: p.title, content: pin, gmpClickable: true });
      mk.addEventListener('gmp-click', () => {
        const d = document.createElement('div');
        d.style.cssText = 'font:14px/1.45 Jost,-apple-system,sans-serif;color:#141619;max-width:250px';
        d.innerHTML = `<b style="display:block">${esc(p.title)}</b>${esc(p.subtitle || '')}`;
        if (onDetails) {
          const b = document.createElement('button');
          b.textContent = 'See details';
          b.style.cssText = 'margin-top:8px;font:600 12px Jost,sans-serif;letter-spacing:.06em;text-transform:uppercase;padding:7px 10px;border-radius:8px;border:0;background:#141619;color:#EEEDEA;cursor:pointer';
          b.onclick = () => { info.close(); onDetails(p.id); };
          d.appendChild(b);
        }
        info.setContent(d); info.open({ map: m, anchor: mk });
      });
      bounds.extend({ lat: p.lat, lng: p.lng });
    }
    if (pts.length > 1) m.fitBounds(bounds, 40);
    else if (pts.length === 1) { m.setCenter(pts[0]); m.setZoom(15); }
  }

  // Open a card in the list and scroll to it.
  function reveal(showTab, id) {
    showTab('list');
    const el = document.getElementById('item-' + id);
    if (!el) return;
    el.open = true;
    el.scrollIntoView({ behavior: 'smooth', block: 'center' });
  }

  return { API, esc, usd, get, post, openHtml, download, offline, tabs, map, reveal };
})();
