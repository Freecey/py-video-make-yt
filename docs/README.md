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
pip install -r requirements.txt
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

### Une image par morceau (meme nom que l’audio)

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

Si un fichier `tracks.json` est present **et** que le JSON est valide, la liste `tracks` definit l’ordre et les paires audio / image. Les fichiers audio qui ne sont pas dans cette liste ne sont pas traites.

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

> Pour `03-outro.mp3` : pas d’`image` dans l’entree, pas de `default_cover` → cherche `03-outro.*` dans le dossier, puis `cover.*` en dernier recours.

#### Reference des champs

| Champ | Niveau | Obligatoire | Description |
|---|---|---|---|
| `tracks` | racine | oui | Liste des pistes a encoder (dans l’ordre) |
| `default_cover` | racine | non | Image de fallback pour toutes les pistes sans `image` explicite |
| `audio` | piste | oui | Chemin relatif du fichier audio (sous le dossier batch) |
| `image` | piste | non | Image specifique a cette piste (priorite maximale) |
| `output` | piste | non | Nom du fichier de sortie (`.mp4` ajoute si absent) |

- Si `output` est absent : le nom de sortie est `<nom_audio>.mp4`.
- Si `image` est absent : ordre de priorite → `default_cover` → image meme nom que l’audio → `cover.*`.

Si `tracks.json` est absent, JSON invalide, ou que sa racine n’est pas un objet JSON, un message d’avertissement s’affiche et le mode **scan du dossier** (tous les audios) est utilise. Si le fichier est un objet JSON valide mais sans cle `tracks`, le scan est utilise silencieusement (sans avertissement).

### Options batch

```bash
# Qualite 4K
python -m video_maker batch mon_album/ -q 4k

# Dossier de sortie personnalise
python -m video_maker batch mon_album/ -o /tmp/videos

# Image de couverture par defaut (fallback) avec un autre nom
python -m video_maker batch mon_album/ --cover-name artwork
```

### Comportement en cas d’erreur (batch)

Si un morceau n’a **aucune** image resolue (ni par `tracks.json`, ni par nom, ni `cover.*`), il est signale dans la sortie et compte comme echec ; les autres morceaux peuvent quand meme etre encodes.

## Ce que fait l'outil avec votre image

L'image est **automatiquement redimensionnee** pour correspondre a la resolution choisie (1920x1080 ou 3840x2160) :

- Le **ratio de l'image est toujours preserve** (pas de deformation)
- L'image est **centree** sur un fond noir
- Les bandes noires (letterboxing) comblent l'espace vide

## Formats de fichiers acceptes

| Type | Extensions |
|------|-----------|
| Image | .jpg, .jpeg, .png, .bmp, .webp, .tiff |
| Audio | .mp3, .wav, .aac, .m4a, .ogg, .opus, .flac, .wma |

## Approbation

**Luna** — testée et approuvée ✅ (23/04/2026)
