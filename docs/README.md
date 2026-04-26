# video-maker-auto — Guide utilisateur

## C'est quoi ?

video-maker-auto cree des videos a partir d'une **image fixe** et d'un **fichier audio**. La video resultante est directement exploitable pour YouTube.

Cas d'usage typique : publier des clips musicaux, podcasts, ou morceaux sur YouTube sans logiciel de montage.

## Installation rapide

Ouvrir un terminal et taper :

```bash
cd video-maker-auto
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
```

Pour le developpement (inclut pytest, ruff, mypy, pytest-cov) :

```bash
pip install -e ".[dev]"
```

Verifier que ffmpeg est installe :

```bash
ffmpeg -version
```

Si absent, l'installer avec `sudo apt install ffmpeg` (Linux) ou `brew install ffmpeg` (macOS).

## Creer une video

### Une seule video

```bash
python -m video_maker single -i ma_photo.jpg -a mon_son.mp3
```

Cela cree `mon_son.mp4` dans le dossier courant, en 1080p.

### Changer la qualite

```bash
# Full HD (defaut)
python -m video_maker single -i cover.jpg -a song.mp3 -q 1080p

# 4K Ultra HD
python -m video_maker single -i cover.jpg -a song.mp3 -q 4k
```

### Preciser le fichier de sortie

```bash
python -m video_maker single -i cover.png -a podcast.wav -o ma_video.mp4
```

### Normalisation audio

Normalise le volume audio selon le standard EBU R128 (recommande pour YouTube) :

```bash
python -m video_maker single -i cover.jpg -a song.mp3 --normalize
```

### Texte superpose (overlay)

Ajoute un texte centre en bas de la video :

```bash
python -m video_maker single -i cover.jpg -a song.mp3 --title "Mon Titre"
```

### Generer une miniature

Cree un fichier JPEG 1280x720 a cote de la video :

```bash
python -m video_maker single -i cover.jpg -a song.mp3 --thumbnail
```

### Options avancees

```bash
# Resolution personnalisee
python -m video_maker single -i cover.jpg -a song.mp3 --resolution 2560x1440

# Bitrate personnalise
python -m video_maker single -i cover.jpg -a song.mp3 --bitrate 16M

# Framerate personnalise
python -m video_maker single -i cover.jpg -a song.mp3 --fps 60

# Toutes les options combinees
python -m video_maker single -i cover.jpg -a song.mp3 \
    --resolution 2560x1440 --bitrate 16M --fps 60 -o ma_video.mp4
```

## Traiter un album complet (batch)

### Mode simple : une image pour tout le dossier

Mettre une couverture globale `cover.*` et les fichiers audio dans le meme dossier :

```
mon_album/
├── cover.jpg
├── 01-premiere-piste.mp3
├── 02-deuxieme-piste.wav
└── 03-derniere-piste.flac
```

```bash
python -m video_maker batch mon_album/
```

Sortie par defaut : `mon_album/output/*.mp4`.

### Une image par morceau (meme nom que l'audio)

Sans fichier manifest : pour chaque fichier audio, si une image porte le **meme nom** (sans extension), elle est utilisee a la place du `cover` global.

```
mon_album/
├── cover.jpg              # utilise pour les pistes sans image dediee
├── 01-intro.mp3
├── 01-intro.png           # utilise pour 01-intro.mp3
├── 02-track.mp3
└── 02-track.jpg           # utilise pour 02-track.mp3
```

### Manifest `tracks.json` (controle fin)

Si un fichier `tracks.json` est present **et** que le JSON est valide, la liste `tracks` definit l'ordre et les paires audio / image. Les fichiers audio qui ne sont pas dans cette liste ne sont pas traites.

#### Exemple complet (tous les champs)

```json
{
  "default_cover": "cover.jpg",
  "tracks": [
    {
      "audio": "01-intro.mp3",
      "image": "art-intro.png",
      "output": "intro"
    },
    {
      "audio": "02-mid.mp3"
    },
    {
      "audio": "03-outro.mp3",
      "image": "art-outro.jpg",
      "output": "fin.mp4"
    }
  ]
}
```

#### Exemple minimal (une image globale pour toutes les pistes)

```json
{
  "default_cover": "cover.jpg",
  "tracks": [
    { "audio": "01-intro.mp3" },
    { "audio": "02-mid.mp3" },
    { "audio": "03-outro.mp3" }
  ]
}
```

#### Exemple sans default_cover (image par piste ou cover.* en fallback)

```json
{
  "tracks": [
    { "audio": "01-intro.mp3", "image": "art-intro.png" },
    { "audio": "02-mid.mp3",   "image": "art-mid.jpg" },
    { "audio": "03-outro.mp3" }
  ]
}
```

> Pour `03-outro.mp3` : pas d'`image` dans l'entree, pas de `default_cover` → cherche `03-outro.*` dans le dossier, puis `cover.*` en dernier recours.

#### Reference des champs

| Champ | Niveau | Obligatoire | Description |
|---|---|---|---|
| `tracks` | racine | oui | Liste des pistes a encoder (dans l'ordre) |
| `default_cover` | racine | non | Image de fallback pour toutes les pistes sans `image` explicite |
| `audio` | piste | oui | Chemin relatif du fichier audio (sous le dossier batch) |
| `image` | piste | non | Image specifique a cette piste (priorite maximale) |
| `output` | piste | non | Nom du fichier de sortie (`.mp4` ajoute si absent) |

- Si `output` est absent : le nom de sortie est `<nom_audio>.mp4`.
- Si `image` est absent : ordre de priorite → `default_cover` → image meme nom que l'audio → `cover.*`.

Si `tracks.json` est absent, JSON invalide, ou que sa racine n'est pas un objet JSON, un message d'avertissement s'affiche et le mode **scan du dossier** (tous les audios) est utilise. Si le fichier est un objet JSON valide mais sans cle `tracks`, le scan est utilise silencieusement (sans avertissement).

### Options batch

```bash
# Qualite 4K
python -m video_maker batch mon_album/ -q 4k

# Dossier de sortie personnalise
python -m video_maker batch mon_album/ -o /tmp/videos

# Image de couverture par defaut (fallback) avec un autre nom
python -m video_maker batch mon_album/ --cover-name artwork

# Encodage parallele avec 4 workers
python -m video_maker batch mon_album/ -j 4

# Ignorer les fichiers deja encodes
python -m video_maker batch mon_album/ --skip-existing

# Avec normalisation et miniatures
python -m video_maker batch mon_album/ --normalize --thumbnail

# Texte superpose sur toutes les videos
python -m video_maker batch mon_album/ --title "Mon Album"
```

### Barre de progression et resume batch

Pendant l'encodage, une barre de progression s'affiche :

```
[=======>          ] 45% | 02-track.mp3
```

A la fin d'un batch, un tableau recapitulatif affiche le temps et la taille par piste :

```
--- Batch summary ---
01-intro.mp4     12.3s   45.2 MB   OK
02-track.mp4     34.1s  112.8 MB   OK
03-outro.mp4      8.7s   32.1 MB   FAIL
```

### Comportement en cas d'erreur (batch)

Si un morceau n'a **aucune** image resolue (ni par `tracks.json`, ni par nom, ni `cover.*`), il est signale dans la sortie et compte comme echec ; les autres morceaux peuvent quand meme etre encodes.

En cas d'echec ffmpeg, l'outil retente automatiquement une fois avec un preset d'encodage plus rapide (ultrafast). Si la deuxieme tentative echoue egalement, la piste est marquee en echec.

### Verification de l'espace disque

Avant un batch, l'outil estime l'espace necessaire et verifie l'espace disponible. Si l'espace est insuffisant, un avertissement s'affiche (l'encodage continue quand meme).

## Mode dry-run (apercu)

Pour voir les commandes ffmpeg qui seraient lancees, sans executer quoi que ce soit :

```bash
python -m video_maker --dry-run single -i cover.jpg -a song.mp3
python -m video_maker --dry-run batch mon_album/
```

## Ce que fait l'outil avec votre image

L'image est **automatiquement redimensionnee** pour correspondre a la resolution choisie (1920x1080 ou 3840x2160) :

- Le **ratio de l'image est toujours preserve** (pas de deformation)
- L'image est **centree** sur le canvas
- Les zones vides sont remplies par un **fond floute** : la meme image, redimensionnee pour couvrir tout le canvas (mode "cover", recadree au centre) puis floutee avec un fort flou gaussien
- Resultat : zero bande noire visible, rendu professionnel meme pour les images au format carre ou portrait

### Desactiver le fond floute

Pour revenir aux bandes noires classiques (utile si l'image couvre deja tout l'ecran) :

```bash
python -m video_maker single -i cover.jpg -a song.mp3 --no-blur-bg
python -m video_maker batch mon_album/ --no-blur-bg
```

## Fichier de configuration

Creer `~/.video-maker.toml` pour definir des options par defaut (les flags CLI ont toujours priorite) :

```toml
[video-maker]
quality = "4k"
blur_bg = false
normalize = true
title = "Mon Album"
```

Ou utiliser un format plat (sans section `[video-maker]`) :

```toml
quality = "4k"
normalize = true
```

Pour utiliser un fichier de config alternatif :

```bash
python -m video_maker --config /chemin/vers/maconfig.toml single -i cover.jpg -a song.mp3
```

## Formats de fichiers acceptes

| Type | Extensions |
|------|-----------|
| Image | .jpg, .jpeg, .png, .bmp, .webp, .tiff |
| Audio | .mp3, .wav, .aac, .m4a, .ogg, .opus, .flac, .wma |

## Toutes les options

### Flags globaux

| Flag | Description | Defaut |
|------|-------------|--------|
| `-v`, `--verbose` | Affiche les messages de debug (ffmpeg stderr complet) | desactive |
| `--config` | Chemin vers le fichier de config | `~/.video-maker.toml` |
| `--dry-run` | Apercu des commandes sans executer ffmpeg | desactive |

### Mode single

| Flag | Description | Defaut |
|------|-------------|--------|
| `-i`, `--image` | Chemin vers l'image | obligatoire |
| `-a`, `--audio` | Chemin vers le fichier audio | obligatoire |
| `-o`, `--output` | Chemin de la video de sortie | `<nom_audio>.mp4` |
| `-q`, `--quality` | Preset : `1080p` ou `4k` | `1080p` |
| `--resolution` | Resolution personnalisee (`WxH`) | du preset |
| `--bitrate` | Bitrate video personnalise | du preset |
| `--fps` | Framerate personnalise | du preset |
| `--no-blur-bg` | Bandes noires au lieu du fond floute | desactive (blur on) |
| `--normalize` | Normalisation audio (EBU R128 / YouTube) | desactive |
| `--title` | Texte superpose (centre, en bas) | aucun |
| `--thumbnail` | Generer une miniature JPEG 1280x720 | desactive |

### Mode batch

| Flag | Description | Defaut |
|------|-------------|--------|
| `input_dir` | Dossier avec les fichiers audio | obligatoire |
| `-o`, `--output-dir` | Dossier de sortie | `<input_dir>/output` |
| `-q`, `--quality` | Preset : `1080p` ou `4k` | `1080p` |
| `--cover-name` | Nom du fichier couverture (sans extension) | `cover` |
| `--no-blur-bg` | Bandes noires | desactive (blur on) |
| `--skip-existing` | Ignorer les fichiers deja encodes | desactive |
| `-j`, `--jobs` | Nombre de workers d'encodage parallele | `1` (sequentiel) |
| `--normalize` | Normalisation audio (EBU R128) | desactive |
| `--title` | Texte superpose sur toutes les videos | aucun |
| `--thumbnail` | Generer des miniatures | desactive |

## Lancer les tests

```bash
# Tests unitaires
python -m pytest tests/ -v

# Tests d'integration (necessite ffmpeg)
python -m pytest tests/ -m integration -v

# Rapport de coverage (seuil : 80%)
make test-cov
```

## Approbation

**Luna** — testee et approuvee (23/04/2026)
