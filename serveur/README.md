# Carte – synchro (serveur du Raspberry Pi)

Code de l'application Home Assistant **« Carte – synchro »** (module local `local_carte_synchro`),
qui synchronise la carte de prospection entre les appareils et envoie le message du matin.

Copie de sauvegarde et historique des versions : **le code qui tourne est celui du dossier
`/addons/carte_synchro` sur le Pi.** Après chaque modification du serveur, mettre à jour ce dossier ici aussi.

## Contenu

| Fichier | Rôle |
|---|---|
| `carte_synchro/serveur.py` | Serveur HTTP (port 8787) : `GET /etats`, `PUT /etat/<appareil>`, photos, `DELETE /etats/anciens?jours=N` |
| `carte_synchro/matin.py` | Message du matin (notification Home Assistant / Telegram) |
| `carte_synchro/config.yaml` | Description du module pour Home Assistant (version, options) |
| `carte_synchro/Dockerfile` | Image Python légère |

Aucun secret ici : le **code d'équipe** et le **jeton Telegram** sont dans les options du module
(Home Assistant → Paramètres → Modules complémentaires → Carte – synchro → Configuration).

## Réinstaller sur un Pi neuf

1. Installer Home Assistant OS et l'application **Terminal** (ou « Terminal & SSH »).
2. Dans le Terminal, recréer le dossier du module local à partir de ce dépôt :
   ```
   mkdir -p /addons/carte_synchro && cd /addons/carte_synchro
   for f in Dockerfile config.yaml serveur.py matin.py; do
     wget -q "https://raw.githubusercontent.com/Yohan51/prospection/main/serveur/carte_synchro/$f" -O "$f"
   done
   ```
3. Home Assistant → Paramètres → Modules complémentaires → Boutique → ⋮ → **Rechercher des mises à jour**.
   « Carte – synchro » apparaît dans **Modules locaux** : l'installer.
4. Onglet **Configuration** : remettre le **code d'équipe** (et les réglages du matin), puis **Démarrer**.
5. Restaurer les données (fiches, photos) depuis une **sauvegarde Home Assistant** qui inclut ce module
   (il faut la **clé de chiffrement** des sauvegardes). À défaut, chaque appareil renverra ses fiches
   à la première synchro.
6. Tailscale : vérifier que le port 8443 publie bien `localhost:8787` (adresse utilisée par la carte et le raccourci « Relais SMS »).

## Historique

- **1.4.0** (9 nov. 2026) : `DELETE /etats/anciens?jours=N` pour supprimer les appareils inactifs (le relais SMS est toujours conservé) ; CORS autorise `DELETE`.
- **1.3.0** : version d'origine (synchro, photos, message du matin).
