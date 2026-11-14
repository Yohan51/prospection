# Mise à jour 1.4.0 -> 1.5.0 de « Carte – synchro » : ne plus jamais proposer de SMS pour un rendez-vous passé.
# A coller dans le Terminal de Home Assistant (voir README). Sauvegarde l'original en .bak.
import re, shutil, sys, os
d = '/addons/carte_synchro'
s_path, c_path = os.path.join(d, 'serveur.py'), os.path.join(d, 'config.yaml')
s = open(s_path, encoding='utf-8').read()
if 'def sans_sms_passes' in s:
    sys.exit('Déjà fait : rien à changer.')
shutil.copy(s_path, s_path + '.bak15'); shutil.copy(c_path, c_path + '.bak15')
def rep(a, b):
    global s
    assert s.count(a) == 1, 'introuvable : ' + a[:50]
    s = s.replace(a, b)
rep("import matin\n", "import matin\nfrom datetime import datetime, timezone\n")
rep("""                        appareils.append({'id': f[:-5], 'etat': json.load(fh)})""",
    """                        appareils.append({'id': f[:-5], 'etat': sans_sms_passes(json.load(fh))})""")
rep("""            empreinte = hashlib.sha1('|'.join(""", """            empreinte = hashlib.sha1(('%d|' % (time.time() // 900)).encode() + '|'.join(""")
rep("def ecrire(chemin, contenu):", '''def sans_sms_passes(etat):
    """Retire des listes « SMS à envoyer » les rendez-vous passés ou à moins d'une heure."""
    items = etat.get('smsAFaire') if isinstance(etat, dict) else None
    if not isinstance(items, list):
        return etat
    limite = time.time() + 3600
    garder = []
    for it in items:
        try:
            if it.get('fin'):
                t = datetime.fromisoformat(it['fin'].replace('Z', '+00:00')).timestamp()
            else:
                t = datetime.strptime(it['rdv'], '%Y-%m-%d %H:%M').replace(tzinfo=timezone.utc).timestamp() - 2 * 3600
        except (KeyError, ValueError, TypeError, AttributeError):
            continue
        if t > limite:
            garder.append(it)
    etat['smsAFaire'] = garder
    return etat


def ecrire(chemin, contenu):''')
compile(s, 'serveur.py', 'exec')
open(s_path, 'w', encoding='utf-8').write(s)
c = open(c_path, encoding='utf-8').read()
c = re.sub(r'^version: "[0-9.]+"', 'version: "1.5.0"', c, count=1, flags=re.M)
open(c_path, 'w', encoding='utf-8').write(c)
print('OK : serveur.py modifié, version 1.5.0. Sauvegardes : serveur.py.bak15 et config.yaml.bak15')
