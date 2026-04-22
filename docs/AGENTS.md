# AGENTS.md — Documentation technique pour agents IA

Ce document decrit l'architecture et les conventions du projet video-maker-auto pour faciliter l'intervention d'agents IA sur la base de code.

## Resume du projet

**Objectif** : Outil CLI Python qui combine une image fixe + un fichier audio en video MP4 optimisee pour YouTube via ffmpeg.

**Stack** : Python 3.10+, ffmpeg (subprocess), Pillow (redimensionnement image), argparse (CLI).

**Dependances** : Pillow (manipulation d'images), pytest (tests). Aucun framework externe.

## Architecture

```
video_maker/
├── __init__.py      # Vide, marque le package
├── cli.py           # Point d'entree CLI, sous-commandes: single, batch
├── encoder.py       # Logique metier: validation, preparation image, encodage ffmpeg, batch
└── settings.py      # Presets qualite (1080p/4k), config encoding YouTube, TypedDict QualityPreset
```

### Flux de donnees

```
Image + Audio
  -> validate_inputs()        verification extensions et existence
  -> _prepare_image()         redimensionnement + letterboxing (Pillow)
  -> subprocess.run(ffmpeg)   encodage H.264 + AAC en MP4
  -> output.mp4
```

L'image est pretraitee par Pillow : redimensionnement + letterboxing sur fond noir. Le filtre ffmpeg `-vf` n'est plus utilise (supprime pour eviter le double traitement).

### Mode batch

```
input_dir/
  -> scan pour cover.* (image)
  -> scan pour fichiers audio (trie par nom)
  -> pour chaque audio: encode_video()
  -> BatchResult(successes, failures)
```

`batch_encode()` retourne un `BatchResult` (dataclass) avec `successes: list[Path]` et `failures: list[tuple[Path, str]]`. Les fichiers en echec sont listes avec la raison.

### Gestion des erreurs

- `encode_video()` leve des exceptions (jamais `sys.exit`).
- `validate_inputs()` leve `FileNotFoundError` ou `ValueError`.
- Si ffmpeg n'est pas installe : `RuntimeError`.
- `batch_encode()` leve `FileNotFoundError` si le dossier n'existe pas, `NotADirectoryError` si le chemin n'est pas un repertoire.
- La CLI (`cli.py`) catche ces exceptions et retourne un code de sortie (0 ou 1).

### Repertoire temporaire

`encode_video()` utilise `tempfile.mkdtemp()` pour le repertoire de travail (image preparee). Le repertoire est nettoye dans un bloc `finally` meme en cas d'erreur.

## Conventions

### Settings (`settings.py`)

- `QualityPreset` : TypedDict avec `resolution`, `video_bitrate`, `frame_rate`.
- `QUALITY_PRESETS` : dictionnaire de presets (`"1080p"`, `"4k"`).
- `ENCODING_SETTINGS` : parametres constants du codec (H.264 High, AAC 48kHz, yuv420p, faststart).
- `SUPPORTED_*_EXTENSIONS` : sets d'extensions valides.

Pour ajouter une nouvelle qualite (ex. 1440p), ajouter une entree dans `QUALITY_PRESETS`.

### Encoder (`encoder.py`)

- `resolve_quality()` : retourne un `QualityPreset`. Leve `ValueError` si inconnu.
- `validate_inputs()` : leve `FileNotFoundError` ou `ValueError`.
- `_prepare_image(path, work_dir, resolution)` : retourne le chemin de l'image preparee. Si deja a la bonne taille, retourne le chemin original. Utilise un context manager `with Image.open(...)` pour eviter les fuites de descripteurs de fichier.
- `encode_video()` : accepte `quality` (str) OU des overrides manuels (`resolution`, `video_bitrate`, `frame_rate`). Les overrides ont priorite sur le preset.
- `BatchResult` : dataclass avec `successes: list[Path]` et `failures: list[tuple[Path, str]]`.
- `batch_encode()` : scan un dossier, matching par stem du fichier image (`cover_name`). Retourne un `BatchResult`.

### CLI (`cli.py`)

- Sous-commandes : `single` et `batch`.
- `main()` retourne un int (0 = succes, 1 = erreur).
- La resolution manuelle est en format `WxH`.
- En mode batch, retourne 1 si au moins un fichier a echoue.

### Tests

- `tests/conftest.py` : fixtures partagees (`tmp_image`, `tmp_audio`, `batch_dir`, `mock_ffmpeg_ok`, `mock_ffmpeg_fail`).
- `tests/test_encoder.py` : tests unitaires sur validation, preparation image, encodage (ffmpeg mocke), batch, resultats partiels.
- `tests/test_cli.py` : tests du parsing CLI, `_parse_resolution`, retours de `main()` (single/batch/help, cas d'erreur).
- ffmpeg est toujours mocke dans les tests unitaires via `unittest.mock.patch`.

### Dependances

- `Pillow>=11.0` : manipulation d'images (resize, canvas, sauvegarde).
- `pytest>=8.0` : framework de test (dev dependency).

## Points d'extension connus

1. **Nouvelle qualite** : ajouter dans `QUALITY_PRESETS` dans `settings.py`.
2. **Ken Burns / zoom lent** : ajouter un filtre ffmpeg `-vf zoompan` dans `encoder.py`.
3. **Overlay texte** : ajouter un filtre `drawtext` dans la commande ffmpeg.
4. **Watermark** : ajouter un deuxieme input image et un filtre `overlay`.
5. **Progression** : parser stderr de ffmpeg (duree/progress) pour afficher un % d'avancement.
6. **Parallelisation batch** : utiliser `concurrent.futures.ProcessPoolExecutor` dans `batch_encode()`.

## Commandes utiles

```bash
# Installer
python3 -m venv .venv && source .venv/bin/activate && pip install -r requirements.txt

# Installer avec dev dependencies
pip install -r requirements.txt && pip install -e ".[dev]"

# Lancer les tests
python -m pytest tests/ -v

# Utilisation single
python -m video_maker single -i cover.jpg -a song.mp3 -q 4k

# Utilisation batch
python -m video_maker batch /music/album -q 1080p
```
