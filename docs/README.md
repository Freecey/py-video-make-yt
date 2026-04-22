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

Placer tous les fichiers dans un meme dossier avec une image de couverture nommee `cover.*` :

```
mon_album/
├── cover.jpg
├── 01-premiere-piste.mp3
├── 02-deuxieme-piste.wav
└── 03-derniere-piste.flac
```

Lancer la commande batch :

```bash
python -m video_maker batch mon_album/
```

Les videos sont generees dans `mon_album/output/`.

### Options batch

```bash
# Qualite 4K
python -m video_maker batch mon_album/ -q 4k

# Dossier de sortie personnalise
python -m video_maker batch mon_album/ -o /tmp/videos

# Image de couverture avec un autre nom
python -m video_maker batch mon_album/ --cover-name artwork
```

## Ce que fait l'outil avec votre image

L'image est **automatiquement redimensionnee** pour correspondre a la resolution choisie (1920x1080 ou 3840x2160) :

- Le **ratio de l'image est toujours preserve** (pas de deformation)
- L'image est **centree** sur un fond noir
- Les bandes noires (letterboxing) comblent l'espace vide

## Formats de fichiers acceptes

| Type | Extensions |
|------|-----------|
| Image | .jpg, .jpeg, .png, .bmp, .webp, .tiff |
| Audio | .mp3, .wav, .aac, .m4a, .ogg, .flac, .wma |
