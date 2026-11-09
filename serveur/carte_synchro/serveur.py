"""Carte – synchro : petit serveur de synchronisation pour la carte de prospection.

Chaque appareil dépose son état complet (portes, R1, salons…) sous son propre nom,
puis récupère ceux des autres et les fusionne lui-même. Rien n'est jamais écrasé
par un autre appareil. Les photos sont stockées une fois, par identifiant.
"""
import hashlib, hmac, json, os, re, time
import matin
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

DATA = os.environ.get('CARTE_DATA', '/data')
ETATS = os.path.join(DATA, 'etats')
PHOTOS = os.path.join(DATA, 'photos')
PORT = int(os.environ.get('CARTE_PORT', '8787'))
ID_OK = re.compile(r'^[A-Za-z0-9_-]{1,80}$')
MAX_ETAT = 30 * 1024 * 1024
MAX_PHOTO = 8 * 1024 * 1024
os.makedirs(ETATS, exist_ok=True)
os.makedirs(PHOTOS, exist_ok=True)


def code_equipe():
    try:
        with open(os.path.join(DATA, 'options.json'), encoding='utf-8') as f:
            return str(json.load(f).get('code_equipe') or '')
    except (OSError, ValueError):
        return os.environ.get('CARTE_CODE', '')


def ecrire(chemin, contenu):
    tmp = chemin + '.tmp'
    with open(tmp, 'wb') as f:
        f.write(contenu)
    os.replace(tmp, chemin)


class Gestion(BaseHTTPRequestHandler):
    server_version = 'CarteSynchro/1.3.0'

    def log_message(self, fmt, *args):
        print('%s %s' % (self.address_string(), (fmt % args).split('?')[0]))

    def entetes_cors(self):
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, PUT, DELETE, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'X-Code, Content-Type, If-None-Match')
        self.send_header('Access-Control-Expose-Headers', 'ETag')
        self.send_header('Access-Control-Max-Age', '86400')

    def repondre(self, code, corps=b'', type_='application/json', autres=None):
        if isinstance(corps, (dict, list)):
            corps = json.dumps(corps, ensure_ascii=False).encode('utf-8')
        self.send_response(code)
        self.entetes_cors()
        if corps:
            self.send_header('Content-Type', type_)
        self.send_header('Content-Length', str(len(corps)))
        self.send_header('Cache-Control', 'no-store')
        for k, v in (autres or {}).items():
            self.send_header(k, v)
        self.end_headers()
        if corps and self.command != 'HEAD':
            self.wfile.write(corps)

    def autorise(self):
        attendu = code_equipe()
        if not attendu:
            self.repondre(503, {'erreur': 'Code d’équipe non réglé dans l’application Home Assistant'})
            return False
        recu = self.headers.get('X-Code', '')
        if not recu and self.path.startswith('/matin/'):
            from urllib.parse import parse_qs, urlparse
            recu = (parse_qs(urlparse(self.path).query).get('code') or [''])[0]
        if not hmac.compare_digest(recu.encode('utf-8'), attendu.encode('utf-8')):
            time.sleep(0.5)
            self.repondre(401, {'erreur': 'Code d’équipe incorrect'})
            return False
        return True

    def lire_corps(self, maxi):
        n = int(self.headers.get('Content-Length') or 0)
        if n <= 0 or n > maxi:
            self.repondre(413 if n > maxi else 400, {'erreur': 'Taille invalide'})
            return None
        return self.rfile.read(n)

    def do_OPTIONS(self):
        self.repondre(204)

    def do_GET(self):
        chemin, _, requete = self.path.partition('?')
        if chemin == '/':
            return self.repondre(200, {'service': 'carte-synchro', 'ok': True})
        if not self.autorise():
            return
        if chemin == '/matin/agendas':
            try:
                cals = matin._ha_get('/calendars')
                txt = 'Agendas vus par Home Assistant (copie leurs noms dans agenda_calendriers pour n’en garder que certains) :\n' + '\n'.join(f"{c['entity_id']}  {c.get('name', '')}" for c in cals) if cals else 'Aucun agenda dans Home Assistant : ajoute d’abord l’intégration CalDAV (iCloud).'
            except Exception as e:
                txt = f'Lecture des agendas impossible : {e}'
            return self.repondre(200, txt.encode('utf-8'), 'text/plain; charset=utf-8')
        if chemin == '/matin/telegram-id':
            return self.repondre(200, matin.telegram_ids(DATA).encode('utf-8'), 'text/plain; charset=utf-8')
        if chemin in ('/matin/apercu', '/matin/envoyer'):
            if chemin == '/matin/envoyer':
                ok, msg = matin.envoyer(DATA, ETATS)
                return self.repondre(200 if ok else 500, msg.encode('utf-8'), 'text/plain; charset=utf-8')
            o = matin.options(DATA)
            titre, corps = matin.resume(ETATS, (o.get('matin_prenom') or '').strip(), calendriers=matin.avec_agenda(o))
            return self.repondre(200, f'{titre}\n\n{corps}'.encode('utf-8'), 'text/plain; charset=utf-8')
        if chemin == '/sante':
            return self.repondre(200, {'ok': True, 'appareils': len(os.listdir(ETATS))})
        if chemin == '/etats':
            sauf = dict(p.split('=', 1) for p in requete.split('&') if '=' in p).get('sauf', '')
            fichiers = sorted(f for f in os.listdir(ETATS) if f.endswith('.json') and f[:-5] != sauf)
            empreinte = hashlib.sha1('|'.join(
                '%s:%d:%d' % (f, os.path.getmtime(os.path.join(ETATS, f)) * 1000, os.path.getsize(os.path.join(ETATS, f)))
                for f in fichiers).encode()).hexdigest()
            etag = '"%s"' % empreinte
            if self.headers.get('If-None-Match') == etag:
                return self.repondre(304, autres={'ETag': etag})
            appareils = []
            for f in fichiers:
                try:
                    with open(os.path.join(ETATS, f), encoding='utf-8') as fh:
                        appareils.append({'id': f[:-5], 'etat': json.load(fh)})
                except (OSError, ValueError):
                    pass
            return self.repondre(200, {'appareils': appareils}, autres={'ETag': etag})
        if chemin == '/photos':
            ids = [f[:-4] for f in os.listdir(PHOTOS) if f.endswith('.jpg')]
            return self.repondre(200, {'photos': ids})
        m = re.match(r'^/photo/([^/]+)$', chemin)
        if m and ID_OK.match(m.group(1)):
            f = os.path.join(PHOTOS, m.group(1) + '.jpg')
            if not os.path.exists(f):
                return self.repondre(404, {'erreur': 'Photo absente'})
            with open(f, 'rb') as fh:
                return self.repondre(200, fh.read(), 'image/jpeg')
        self.repondre(404, {'erreur': 'Inconnu'})

    def do_PUT(self):
        if not self.autorise():
            return
        m = re.match(r'^/etat/([^/?]+)$', self.path)
        if m and ID_OK.match(m.group(1)):
            corps = self.lire_corps(MAX_ETAT)
            if corps is None:
                return
            try:
                etat = json.loads(corps)
                assert etat.get('app') == 'carte-prospection' and isinstance(etat.get('portes'), list)
            except (ValueError, AssertionError, AttributeError):
                return self.repondre(400, {'erreur': 'Données illisibles'})
            ecrire(os.path.join(ETATS, m.group(1) + '.json'), corps)
            return self.repondre(200, {'ok': True})
        m = re.match(r'^/photo/([^/?]+)$', self.path)
        if m and ID_OK.match(m.group(1)):
            corps = self.lire_corps(MAX_PHOTO)
            if corps is None:
                return
            if not corps.startswith(b'\xff\xd8'):
                return self.repondre(400, {'erreur': 'Pas une photo JPEG'})
            ecrire(os.path.join(PHOTOS, m.group(1) + '.jpg'), corps)
            return self.repondre(200, {'ok': True})
        self.repondre(404, {'erreur': 'Inconnu'})

    def do_DELETE(self):
        if not self.autorise():
            return
        chemin, _, requete = self.path.partition('?')
        if chemin == '/etats/anciens':
            from urllib.parse import parse_qs
            try:
                jours = max(1.0, float((parse_qs(requete).get('jours') or ['2'])[0]))
            except ValueError:
                jours = 2.0
            limite = time.time() - jours * 86400
            supprimes = []
            for f in os.listdir(ETATS):
                if not f.endswith('.json') or f == 'relais-sms.json':
                    continue
                p = os.path.join(ETATS, f)
                try:
                    if os.path.getmtime(p) < limite:
                        os.remove(p)
                        supprimes.append(f[:-5])
                except OSError:
                    pass
            return self.repondre(200, {'ok': True, 'supprimes': supprimes})
        self.repondre(404, {'erreur': 'Inconnu'})



if __name__ == '__main__':
    print('Carte – synchro démarrée sur le port %d (code d’équipe %s)' % (PORT, 'réglé' if code_equipe() else 'NON RÉGLÉ'))
    matin.demarrer(DATA, ETATS)
    ThreadingHTTPServer(('0.0.0.0', PORT), Gestion).serve_forever()
