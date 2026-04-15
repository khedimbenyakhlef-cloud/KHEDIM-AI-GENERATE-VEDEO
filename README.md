# 🎬 KHEDIM AI — Generate Video

**Studio de génération vidéo IA haute qualité avec TPU v5 / v6e**
Fondé par **KHEDIM BENYAKHLEF**

---

## ✨ Fonctionnalités

| Fonctionnalité | Détail |
|---|---|
| 🎬 Vidéo longue durée | Jusqu'à 10 minutes, segmentation automatique |
| 🎵 Musique IA | MusicGen (Meta) — 9 styles musicaux |
| 🎙️ Voix off IA | Coqui XTTS v2 — voix naturelles FR |
| 🖼️ Image HD | SDXL jusqu'à 4K |
| 🔒 Auth PIN | Code PIN hashé SHA-256, token de session |
| ⚡ TPU v5/v6e | Optimisé bfloat16, mark_step() XLA |
| 🤖 Style auto | Détection par analyse de mots-clés (sans API externe) |

---

## 🚀 Démarrage rapide

### Architecture

```
KHEDIM AI
├── backend/        → Serveur Flask (Render.com)
│   └── app.py
├── frontend/       → Interface utilisateur
│   └── index.html
├── kaggle/         → Notebook TPU Colab
│   └── KHEDIM_AI_TPU_v5_NOTEBOOK.ipynb
├── outputs/        → Vidéos/images générées (gitignored)
├── logs/           → Logs serveur (gitignored)
├── requirements.txt
├── render.yaml
├── .gitignore
└── README.md
```

### Étape 1 — Lancer le Notebook Colab

1. Ouvrez [Google Colab](https://colab.research.google.com)
2. Importez `kaggle/KHEDIM_AI_TPU_v5_NOTEBOOK.ipynb`
3. Menu **Exécution → Modifier le type d'exécution** → sélectionnez **TPU v2-8**
4. Exécutez **Cellule 1** — Installation (environ 5 minutes)
5. Exécutez **Cellule 2** — Init TPU + chargement modèles (environ 3 minutes)
6. Dans la **Cellule 3**, renseignez votre token ngrok :
   ```python
   NGROK_TOKEN = 'votre_token_ici'  # https://dashboard.ngrok.com/auth
   ```
7. Exécutez la **Cellule 3** — copiez l'URL ngrok affichée

### Étape 2 — Déployer le Backend (Render.com)

1. Créez un compte sur [Render.com](https://render.com)
2. "New Web Service" → connectez votre dépôt GitHub
3. Dans les variables d'environnement, ajoutez :
   - `ACCESS_PIN` : votre code PIN (ex: `2022002`)
   - `TPU_URL` : l'URL ngrok du notebook (ex: `https://xxxx.ngrok.io`)
4. Cliquez **Deploy**

### Étape 3 — Utiliser l'interface

1. Ouvrez l'URL Render.com
2. Entrez votre code PIN
3. Dans la sidebar **"URL Notebook"**, collez l'URL ngrok
4. Décrivez votre scène → cliquez **Générer la Vidéo** 🎬

---

## 🔐 Authentification

Le système utilise un **code PIN hashé SHA-256** avec token de session.

- **Aucune clé Anthropic n'est requise** — la détection de style se fait par analyse locale
- Le PIN ne transite jamais en clair
- Les tokens de session expirent après 24h
- Protection anti-brute-force (délai 1s sur PIN incorrect)

**Changer le PIN** : définissez la variable d'environnement `ACCESS_PIN` dans Render.com.

---

## ⚡ Compatibilité TPU

| TPU | Résolution | Qualité |
|---|---|---|
| TPU v5 / v6e-32 | 3840×2160 | 4K |
| TPU v5 / v6e-8 | 1920×1080 | 1080p |
| TPU v2-8 / v6e-4 | 1280×720 | 720p |
| TPU v6e-1 | 768×432 | SD+ |
| CPU / GPU T4 | 512×288 | SD |

Le notebook détecte automatiquement le TPU disponible et adapte la résolution.

---

## 🎨 Styles visuels disponibles

| Style | Description |
|---|---|
| Cinématique | Lumières dramatiques, film grain, 4K HDR |
| Cyberpunk | Néons, pluie, ambiance Blade Runner |
| Nature | Heure dorée, grand angle, qualité documentaire |
| Sci-Fi | Nébuleuses, technologie futuriste, qualité IMAX |
| Film Noir | Noir & blanc, ombres expressionnistes |
| Fantasy | Magie, bioluminescence, style Tolkien |
| Horreur | Brume, lune, tension atmosphérique |
| Romantique | Bokeh chaud, lumière dorée, 4K romantique |
| Épique | Armées massives, explosions cinématiques |

La **détection automatique** analyse votre prompt et choisit le style optimal.

---

## 🛠️ Variables d'environnement

| Variable | Description | Défaut |
|---|---|---|
| `ACCESS_PIN` | Code PIN d'accès | `2022002` |
| `TPU_URL` | URL ngrok du notebook | `NOT_CONFIGURED` |
| `PORT` | Port du serveur | `8765` |

---

## 📋 Dépendances backend

```
flask==3.0.3
flask-cors==4.0.1
requests==2.32.3
python-dotenv==1.0.1
gunicorn==22.0.0
```

---

## 📄 Licence

Projet privé — KHEDIM BENYAKHLEF — Tous droits réservés.
