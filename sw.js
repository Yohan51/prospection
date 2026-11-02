/* Carte de prospection : fonctionnement sans réseau.
   - L'appli (page, Leaflet, icônes) : réseau d'abord, copie locale si le réseau manque ou traîne.
   - Les fonds de carte déjà vus : gardés sur le téléphone pour être réaffichés hors réseau.
   - Les adresses, itinéraires et la synchro ne passent pas par ici : ils attendent le retour du réseau. */
const VERSION = 'carte-v1';
const COQUILLE = ['./', './index.html', './leaflet.js', './leaflet.css', './manifest.webmanifest', './icon-180.png', './icon-512.png'];
const TUILES = 'carte-tuiles', POLICES = 'carte-polices', MAX_TUILES = 2500;

self.addEventListener('install', e => {
  e.waitUntil(caches.open(VERSION).then(c => c.addAll(COQUILLE)).then(() => self.skipWaiting()));
});
self.addEventListener('activate', e => {
  e.waitUntil(caches.keys()
    .then(cles => Promise.all(cles.filter(k => ![VERSION, TUILES, POLICES].includes(k)).map(k => caches.delete(k))))
    .then(() => self.clients.claim()));
});

// Réseau d'abord, mais pas plus de 4 s d'attente quand une copie locale existe
async function reseauDabord(req) {
  const cache = await caches.open(VERSION);
  const copie = await cache.match(req, { ignoreSearch: true }) || (req.mode === 'navigate' ? await cache.match('./index.html') : null);
  const reseau = fetch(req).then(r => { if (r.ok) cache.put(req, r.clone()); return r; });
  if (!copie) return reseau;
  const delai = new Promise(ok => setTimeout(() => ok(null), 4000));
  try { return (await Promise.race([reseau, delai])) || copie; } catch (e) { return copie; }
}
let ajouts = 0;
async function rogner(cache) {
  if (++ajouts % 100) return;
  const cles = await cache.keys();
  for (let i = 0; i < cles.length - MAX_TUILES; i++) await cache.delete(cles[i]);
}
async function cacheDabord(nom, req, opaqueOk) {
  const cache = await caches.open(nom);
  const copie = await cache.match(req);
  if (copie) return copie;
  try {
    const r = await fetch(req);
    if (r.ok || (opaqueOk && r.type === 'opaque')) { cache.put(req, r.clone()); if (nom === TUILES) rogner(cache); }
    return r;
  } catch (e) { return Response.error(); }
}

self.addEventListener('fetch', e => {
  const req = e.request;
  if (req.method !== 'GET') return;
  const url = new URL(req.url);
  if (url.origin === self.location.origin) return e.respondWith(reseauDabord(req));
  if (url.hostname === 'tile.openstreetmap.org' || (url.hostname === 'data.geopf.fr' && url.pathname.startsWith('/wmts'))) return e.respondWith(cacheDabord(TUILES, req, false));
  if (/^fonts\.(googleapis|gstatic)\.com$/.test(url.hostname)) return e.respondWith(cacheDabord(POLICES, req, true));
});
