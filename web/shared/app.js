// Shared by all three features: API base, escaping, nav, List/Map tabs, Google Maps.
// Google Maps: Maps JavaScript API only. The key comes from GET /config (GOOGLE_MAPS_API_KEY in .env).

const VDD = (() => {
  const API = new URLSearchParams(location.search).get('api') || (location.protocol.startsWith('http') ? location.origin : 'http://localhost:8000');
  const esc = s => String(s ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'})[c]);
  const NYC = { lat: 40.7128, lng: -73.97 };

  function nav(current){
    const links = [['/case/', 'Case view'], ['/voucher-guard/', 'Voucher Guard'], ['/open-doors/', 'Open Doors'], ['/shelter-match/', 'Shelter Match']];
    const logo = '<svg viewBox="0 0 32 32" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M3.5 15 L16 4.5 L28.5 15"/><path d="M7 12.5 V27.5 H25 V12.5"/><path d="M13.5 27.5 V19.5 H18.5 V27.5"/></svg>';
    return `<nav class="nav" aria-label="Features"><a class="home" href="/">${logo}Homeward.</a>${
      links.map(([href, label]) => `<a href="${href}"${label === current ? ' aria-current="page"' : ''}>${label}</a>`).join('')}</nav>`;
  }

  // tabs(container, {list: el, map: el}, onShowMap): accessible List/Map switcher.
  function tabs(host, panels, onShowMap){
    host.innerHTML = `<div class="tabs" role="tablist"><button role="tab" aria-selected="true" data-t="list">List</button><button role="tab" aria-selected="false" data-t="map">Map</button></div>`;
    const show = t => {
      host.querySelectorAll('button').forEach(b => b.setAttribute('aria-selected', String(b.dataset.t === t)));
      panels.list.hidden = t !== 'list'; panels.map.hidden = t !== 'map';
      if (t === 'map' && onShowMap) onShowMap();
    };
    host.querySelectorAll('button').forEach(b => b.onclick = () => show(b.dataset.t));
    return show;
  }

  let mapsPromise = null;
  function loadMaps(){
    if (mapsPromise) return mapsPromise;
    mapsPromise = fetch(API + '/config').then(r => r.json()).then(cfg => new Promise((resolve, reject) => {
      if (!cfg.google_maps_api_key) return reject(new Error('no-key'));
      window.__vddMapsReady = () => resolve(window.google.maps);
      const s = document.createElement('script');
      s.src = `https://maps.googleapis.com/maps/api/js?key=${encodeURIComponent(cfg.google_maps_api_key)}&v=weekly&libraries=marker&loading=async&callback=__vddMapsReady`;
      s.async = true; s.onerror = () => reject(new Error('load-failed'));
      document.head.appendChild(s);
    }));
    return mapsPromise;
  }

  // renderMap(el, points, {onDetails}) where points = [{id, lat, lng, title, subtitle, color}]
  // Points without coordinates are counted and listed as "not on map".
  async function renderMap(el, points, opts = {}){
    const onMap = points.filter(p => p.lat != null && p.lng != null);
    const off = points.length - onMap.length;
    const noteEl = el.nextElementSibling && el.nextElementSibling.classList.contains('map-note') ? el.nextElementSibling : null;
    if (noteEl) noteEl.textContent = off ? `${onMap.length} on the map. ${off} without an address are in the List tab only.` : `${onMap.length} on the map.`;
    let maps;
    try { maps = await loadMaps(); }
    catch (e) {
      el.innerHTML = `<div class="map-fallback">${e.message === 'no-key'
        ? 'Map needs a Google Maps key: add <code>GOOGLE_MAPS_API_KEY</code> to <code>.env</code> and restart the API.'
        : 'Couldn\'t load Google Maps.'}<br>Meanwhile, open any place in Google Maps: ${onMap.slice(0, 8).map(p =>
          `<a href="https://www.google.com/maps/search/?api=1&query=${p.lat},${p.lng}" target="_blank" rel="noopener">${esc(p.title)}</a>`).join(' · ')}${onMap.length > 8 ? ' …' : ''}</div>`;
      return;
    }
    const map = new maps.Map(el, { center: NYC, zoom: 11, mapId: 'DEMO_MAP_ID', colorScheme: 'DARK', streetViewControl: false, mapTypeControl: false });
    const info = new maps.InfoWindow();
    const bounds = new maps.LatLngBounds();
    for (const p of onMap){
      // Grayscale pins that differ by shape/contrast, not hue: solid (paper), ring (dark with paper border), muted (gray).
      const PIN = { solid: ['#EEEDEA', '#141619', '#141619'], ring: ['#141619', '#EEEDEA', '#EEEDEA'], muted: ['#6D7178', '#EEEDEA', '#EEEDEA'] };
      const [bg, border, glyph] = PIN[p.color] || PIN.solid;
      const pin = new maps.marker.PinElement({ background: bg, borderColor: border, glyphColor: glyph });
      const m = new maps.marker.AdvancedMarkerElement({ map, position: { lat: p.lat, lng: p.lng }, title: p.title, content: pin, gmpClickable: true });
      m.addEventListener('gmp-click', () => {
        const div = document.createElement('div'); div.className = 'iw';
        div.innerHTML = `<b>${esc(p.title)}</b>${esc(p.subtitle || '')}`;
        if (opts.onDetails){
          const b = document.createElement('button'); b.textContent = 'See details in list';
          b.onclick = () => { info.close(); opts.onDetails(p.id); };
          div.appendChild(b);
        }
        info.setContent(div); info.open({ map, anchor: m });
      });
      bounds.extend({ lat: p.lat, lng: p.lng });
    }
    if (onMap.length > 1) map.fitBounds(bounds, 40);
    else if (onMap.length === 1) { map.setCenter(onMap[0]); map.setZoom(15); }
  }

  // Switch to the list and open + highlight one <details id="item-...">.
  function reveal(showTab, id){
    showTab('list');
    const el = document.getElementById('item-' + id);
    if (!el) return;
    el.open = true; el.scrollIntoView({ behavior: 'smooth', block: 'center' });
    el.classList.remove('flash'); void el.offsetWidth; el.classList.add('flash');
  }

  return { API, esc, nav, tabs, renderMap, reveal };
})();
