"""Message du matin : ce que la journée réserve, d'après la carte synchronisée."""
import json, os, threading, time, urllib.request
from datetime import datetime, date, timedelta

try:
    from zoneinfo import ZoneInfo
    FUSEAU = ZoneInfo(os.environ.get('TZ') or 'Europe/Paris')
except Exception:  # pas de base de fuseaux : on reste en UTC
    FUSEAU = None

JOURS = ['lun', 'mar', 'mer', 'jeu', 'ven', 'sam', 'dim']
NOMS_JOURS = ['lundi', 'mardi', 'mercredi', 'jeudi', 'vendredi', 'samedi', 'dimanche']
MOIS = ['janvier', 'février', 'mars', 'avril', 'mai', 'juin', 'juillet', 'août', 'septembre', 'octobre', 'novembre', 'décembre']


def maintenant():
    return datetime.now(FUSEAU) if FUSEAU else datetime.now()


def cle(s):
    import unicodedata
    s = unicodedata.normalize('NFD', str(s or '').lower())
    return ''.join(c for c in s if c.isalnum())


def etat_fusionne(dossier):
    """Réunit les portes de tous les appareils : pour chaque porte, la version la plus récente."""
    portes, rues = {}, {}
    for f in os.listdir(dossier):
        if not f.endswith('.json'):
            continue
        try:
            with open(os.path.join(dossier, f), encoding='utf-8') as fh:
                e = json.load(fh)
        except (OSError, ValueError):
            continue
        for p in e.get('portes') or []:
            q = portes.get(p.get('id'))
            if not q or (p.get('maj') or '') > (q.get('maj') or ''):
                portes[p.get('id')] = p
        for k, r in (e.get('rues') or {}).items():
            if k not in rues or (r.get('maj') or '') > (rues[k].get('maj') or ''):
                rues[k] = r
    return [p for p in portes.values() if not p.get('supprime')], rues


def etape(p):
    s = p.get('suivi') or []
    if s:
        return s[-1].get('etape')
    if p.get('r1') or p.get('statut') == 'r1':
        return 'r1'
    return None


def court(p):
    if p.get('rue'):
        return f"{p.get('numero') or ''} {p['rue']}".strip()
    c = p.get('contact') or {}
    return (p.get('adresse') or '').split(' 51')[0] or c.get('nom') or 'adresse inconnue'


def nom_client(p):
    for src in (p.get('r1'), p.get('aRappeler'), p.get('contact')):
        if src and src.get('nom'):
            return src['nom']
    return ''


def a_moi(p, prenom, champ=None):
    if not prenom:
        return True
    qui = (champ or {}).get('par') if champ else None
    if not qui:
        vs = p.get('visites') or []
        qui = (vs[-1].get('auteur') if vs else None) or p.get('auteur')
    return cle(qui) == cle(prenom) or not qui


def heure(h):
    return (h or '18:00').replace(':', 'h')


def _ha_get(chemin):
    jeton = os.environ.get('SUPERVISOR_TOKEN')
    if not jeton:
        raise RuntimeError('accès à Home Assistant indisponible')
    req = urllib.request.Request(f'http://supervisor/core/api{chemin}', headers={'Authorization': f'Bearer {jeton}'})
    with urllib.request.urlopen(req, timeout=20) as r:
        return json.load(r)


# Les rendez-vous que la carte a elle-même mis dans le Calendrier : déjà listés, on ne les répète pas
DEJA_DANS_LA_CARTE = ('R1 –', 'R2 –', '📞 Rappeler')


def agenda(jour, calendriers=''):
    """Rendez-vous du jour dans les agendas connectés à Home Assistant (iCloud via CalDAV, Google…)."""
    debut = datetime(jour.year, jour.month, jour.day, tzinfo=FUSEAU)
    fin = debut + timedelta(days=1)
    voulus = [c.strip() for c in (calendriers or '').split(',') if c.strip()]
    ids = voulus or [c['entity_id'] for c in _ha_get('/calendars')]
    evts, vus = [], set()
    for cid in ids:
        if not cid.startswith('calendar.'):
            cid = 'calendar.' + cid
        try:
            liste = _ha_get(f"/calendars/{cid}?start={debut.isoformat().replace('+', '%2B')}&end={fin.isoformat().replace('+', '%2B')}")
        except Exception:
            continue
        for e in liste:
            titre = (e.get('summary') or 'Sans titre').strip()
            if titre.startswith(DEJA_DANS_LA_CARTE):
                continue
            d = e.get('start') or {}
            if 'dateTime' in d:
                h = datetime.fromisoformat(d['dateTime']).astimezone(FUSEAU).strftime('%Hh%M') if FUSEAU else d['dateTime'][11:16].replace(':', 'h')
            else:
                h = ''
            cle_e = (h, titre)
            if cle_e in vus:
                continue
            vus.add(cle_e)
            lieu = (e.get('location') or '').split('\n')[0].strip()
            evts.append((h or '00h00', f"{h + ' · ' if h else 'Toute la journée · '}{titre}{' · ' + lieu if lieu else ''}"))
    return [t for _, t in sorted(evts)]


def resume(dossier, prenom='', aujourdhui=None, calendriers=None):
    auj = aujourdhui or maintenant().date()
    j = auj.isoformat()
    hier = (auj - timedelta(days=1)).isoformat()
    portes, rues = etat_fusionne(dossier)
    lignes = []

    rdv = []
    for p in portes:
        r1, et = p.get('r1') or {}, etape(p)
        if r1.get('date') == j and et == 'r1' and a_moi(p, prenom, r1):
            rdv.append((r1.get('heure') or '18:00', f"R1 {heure(r1.get('heure'))} · {nom_client(p) or 'client'} · {court(p)}"))
        if et == 'r2':
            r2 = next((e.get('rdv') for e in reversed(p.get('suivi') or []) if e.get('etape') == 'r2' and e.get('rdv')), None)
            if r2 and r2.get('date') == j and a_moi(p, prenom):
                rdv.append((r2.get('heure') or '18:00', f"R2 {heure(r2.get('heure'))} · {nom_client(p) or 'client'} · {court(p)}"))
    if rdv:
        lignes.append('📅 ' + ('Rendez-vous :' if len(rdv) > 1 else 'Rendez-vous'))
        lignes += ['   ' + t for _, t in sorted(rdv)]

    if calendriers is not None:
        try:
            evts = agenda(auj, calendriers)
        except Exception:
            evts = None
        if evts:
            lignes.append('🗓 Agenda :')
            lignes += ['   ' + t for t in evts[:8]]
            if len(evts) > 8:
                lignes.append(f'   … et {len(evts) - 8} autres')
        elif evts is None:
            lignes.append('🗓 Agenda indisponible pour le moment')

    rappels = []
    for p in portes:
        r = p.get('aRappeler') or {}
        if p.get('statut') == 'rappel' and r.get('date') and r['date'] <= j and a_moi(p, prenom):
            retard = ' (en retard)' if r['date'] < j else f" à {heure(r.get('heure'))}"
            rappels.append((r['date'] + (r.get('heure') or ''), f"{r.get('nom') or court(p)}{retard}{' · ' + r['tel'] if r.get('tel') else ''}"))
    if rappels:
        lignes.append(f"📞 {len(rappels)} à rappeler :")
        lignes += ['   ' + t for _, t in sorted(rappels)[:6]]
        if len(rappels) > 6:
            lignes.append(f"   … et {len(rappels) - 6} autres")

    devis = []
    for p in portes:
        s = p.get('suivi') or []
        if s and s[-1].get('etape') == 'devis' and a_moi(p, prenom):
            jours = (auj - date.fromisoformat(s[-1].get('date', j)[:10])).days
            if jours >= 7:
                devis.append(f"{nom_client(p) or court(p)} · {jours} j")
    if devis:
        lignes.append(f"📄 {len(devis)} devis à relancer : " + ', '.join(devis[:4]) + (' …' if len(devis) > 4 else ''))

    sans_suite = [p for p in portes if etape(p) == 'r1' and (p.get('r1') or {}).get('date', j) < j and a_moi(p, prenom, p.get('r1'))]
    if sans_suite:
        lignes.append(f"🔁 {len(sans_suite)} R1 fait{'s' if len(sans_suite) > 1 else ''} sans suite notée (R2, devis ou signé ?)")

    a_refaire = [r.get('rue') for r in rues.values() if r.get('terminee') and r.get('refaire') and r['refaire'] <= j]
    if a_refaire:
        lignes.append('🏠 Rue' + ('s' if len(a_refaire) > 1 else '') + ' à refaire : ' + ', '.join(a_refaire[:3]))

    n = r1 = 0
    for p in portes:
        for v in p.get('visites') or []:
            if v.get('canal') == 'salon' or not (v.get('date') or '').startswith(hier):
                continue
            if prenom and cle(v.get('auteur')) != cle(prenom):
                continue
            n += 1
            r1 += v.get('statut') == 'r1'
    # les dates de visite sont en UTC : on accepte l'approximation d'une heure en début de journée
    if n:
        lignes.append(f"📊 Hier : {n} porte{'s' if n > 1 else ''}, {r1} R1")

    titre = f"Bonjour{(' ' + prenom) if prenom else ''} · {NOMS_JOURS[auj.weekday()]} {auj.day} {MOIS[auj.month - 1]}"
    corps = '\n'.join(lignes) if lignes else "Rien d'urgent aujourd'hui : ni rappel, ni rendez-vous, ni devis à relancer. Bonne prospection !"
    return titre, corps


def avec_agenda(o):
    """None = agenda désactivé ; '' = tous les agendas ; sinon la liste choisie."""
    return (o.get('agenda_calendriers') or '').strip() if o.get('agenda_actif', True) else None


def options(data):
    try:
        with open(os.path.join(data, 'options.json'), encoding='utf-8') as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def _poster(url, charge, entetes=None):
    req = urllib.request.Request(url, data=json.dumps(charge).encode(), headers=dict({'Content-Type': 'application/json'}, **(entetes or {})), method='POST')
    with urllib.request.urlopen(req, timeout=20) as r:
        return r.status


def _html(t):
    return str(t).replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')


def envoyer(data, dossier):
    """Envoie le message du matin sur Telegram et/ou en notification Home Assistant, selon les réglages."""
    o = options(data)
    titre, corps = resume(dossier, (o.get('matin_prenom') or '').strip(), calendriers=avec_agenda(o))
    lien = (o.get('matin_lien_carte') or '').strip()
    bilan = []
    jeton_tg, chat_tg = (o.get('telegram_jeton') or '').strip(), str(o.get('telegram_chat_id') or '').strip()
    if jeton_tg and chat_tg:
        texte = f"<b>{_html(titre)}</b>\n\n{_html(corps)}" + (f'\n\n<a href="{_html(lien)}">Ouvrir la carte</a>' if lien else '')
        for chat in [c.strip() for c in chat_tg.split(',') if c.strip()]:
            try:
                _poster(f'https://api.telegram.org/bot{jeton_tg}/sendMessage',
                        {'chat_id': chat, 'text': texte, 'parse_mode': 'HTML', 'disable_web_page_preview': True})
                bilan.append((True, f'Telegram : envoyé à {chat}'))
            except Exception as e:
                bilan.append((False, f'Telegram : refusé ({e}) — vérifie le jeton et que tu as écrit /start au robot'))
    service = (o.get('matin_notification') or '').strip().replace('notify.', '')
    if service:
        jeton = os.environ.get('SUPERVISOR_TOKEN')
        if not jeton:
            bilan.append((False, 'Notification : accès à Home Assistant indisponible'))
        else:
            charge = {'title': titre, 'message': corps}
            if lien:
                charge['data'] = {'url': lien, 'clickAction': lien}
            try:
                _poster(f'http://supervisor/core/api/services/notify/{service}', charge, {'Authorization': f'Bearer {jeton}'})
                bilan.append((True, f'Notification : envoyée à {service}'))
            except Exception as e:
                bilan.append((False, f'Notification : refusée par Home Assistant ({e})'))
    if not bilan:
        return False, 'Rien de réglé : remplis telegram_jeton + telegram_chat_id, ou matin_notification'
    return all(ok for ok, _ in bilan), ' · '.join(m for _, m in bilan)


def telegram_ids(data):
    """Liste les conversations qui ont écrit au robot : sert à trouver son telegram_chat_id."""
    jeton = (options(data).get('telegram_jeton') or '').strip()
    if not jeton:
        return "Remplis d'abord telegram_jeton dans la configuration, redémarre l'application, puis écris /start à ton robot sur Telegram."
    try:
        with urllib.request.urlopen(f'https://api.telegram.org/bot{jeton}/getUpdates', timeout=20) as r:
            j = json.load(r)
    except Exception as e:
        return f'Telegram refuse le jeton ({e}). Vérifie-le dans la configuration.'
    vus = {}
    for u in j.get('result', []):
        m = u.get('message') or u.get('edited_message') or {}
        c = m.get('chat') or {}
        if c.get('id'):
            vus[c['id']] = ' '.join(filter(None, [c.get('first_name'), c.get('last_name'), c.get('title')])) or c.get('username') or ''
    if not vus:
        return "Aucun message reçu par le robot. Ouvre ton robot sur Telegram, écris /start, puis recharge cette page."
    return 'Conversations trouvées (copie le numéro dans telegram_chat_id) :\n' + '\n'.join(f'{i}  {n}' for i, n in vus.items())


def boucle(data, dossier):
    marque = os.path.join(data, 'matin-dernier-envoi.txt')
    try:
        with open(marque) as f:
            deja = date.fromisoformat(f.read().strip())
    except (OSError, ValueError):
        deja = None
    while True:
        try:
            o = options(data)
            if o.get('matin_actif', True):
                t = maintenant()
                jours = [x.strip()[:3].lower() for x in str(o.get('matin_jours') or 'lun,mar,mer,jeu,ven').split(',')]
                h = str(o.get('matin_heure') or '07:20')
                if JOURS[t.weekday()] in jours and t.strftime('%H:%M') >= h and deja != t.date() and t.strftime('%H:%M') < '12:00':
                    ok, msg = envoyer(data, dossier)
                    print(f"Message du matin : {msg}")
                    deja = t.date()
                    try:
                        with open(marque, 'w') as f:
                            f.write(deja.isoformat())
                    except OSError:
                        pass
        except Exception as e:
            print('Message du matin : erreur', e)
        time.sleep(30)


def demarrer(data, dossier):
    threading.Thread(target=boucle, args=(data, dossier), daemon=True).start()
