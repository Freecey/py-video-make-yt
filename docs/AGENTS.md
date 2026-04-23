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
├── __main__.py      # Active `python -m video_maker` (appelle cli.main())
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

La commande ffmpeg utilise `-map 0:v:0 -map 1:a:0` pour lier l’image bouclee au flux video et **uniquement le premier flux audio** du fichier audio. Les fichiers M4A/MP3 avec pochette embarquee en flux MJPEG ne perturbent plus la selection de flux.

L'image est pretraitee par Pillow : redimensionnement + letterboxing sur fond noir. Le filtre ffmpeg `-vf` n'est plus utilise (supprime pour eviter le double traitement).

### Mode batch

Fichier optionnel : `tracks.json` (nom defini par `TRACKS_MANIFEST_FILENAME` dans `settings.py`).

### Schema `tracks.json`

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
      "audio": "subdir/03-outro.mp3",
      "output": "outro.mp4"
    }
  ]
}
```

Regles de validation par champ :

| Champ | Niveau | Type | Requis | Comportement si invalide |
|---|---|---|---|---|
| `tracks` | racine | array | oui (si manifest utilise) | warning + scan |
| `default_cover` | racine | string | non | ignore si absent/vide |
| `audio` | piste | string | oui | entree silencieusement ignoree |
| `image` | piste | string | non | fallback vers `default_cover` / name-match / cover |
| `output` | piste | string | non | defaut : `<audio_stem>.mp4` ; `.mp4` ajoute si absent |

Contraintes : tous les chemins (`audio`, `image`, `default_cover`) sont des chemins **relatifs a `input_dir`** ; tout chemin pointant hors de `input_dir` (via `..`) est rejete (`_file_in_input_dir` / `_is_under_dir`).

**Resolution des paires** (`_resolve_track_pairs` dans `encoder.py`) :

1. **Manifest valide** : `tracks` est une liste non vide. Chaque entree a au minimum `audio` (chemin relatif sous `input_dir`). Champs optionnels : `image`, `output`. Cle racine optionnelle : `default_cover`. Les entrees dont le champ `audio` est absent, vide, hors de `input_dir`, ou avec une extension non supportee sont **silencieusement ignorees** (aucune pre-failure, aucun avertissement).
2. **Image par piste** (ordre de priorite) : `image` sur la piste, puis `default_cover`, puis image avec le **meme stem** que l’audio, puis `cover.*` (`--cover-name`, defaut `cover`).
3. **Sans manifest**, **JSON invalide**, **racine JSON n'est pas un objet** (ex. tableau), ou **`tracks` n'est pas une liste** : avertissement stderr, scan de tous les fichiers audio (tries), meme logique d'image sans le manifest.
4. **`tracks.json` present et dict valide, mais sans cle `tracks`** (ex. `{"default_cover": "cover.jpg"}`) : aucun avertissement, fallback silencieux vers scan. Le champ `default_cover` eventuel est ignore car le scan n'utilise pas le manifest. Mode retourne : `"scan"`.
5. **Securite** : les chemins du manifest sont resolus sous `input_dir` (pas d’`..` sortant du dossier) via `_file_in_input_dir` / `_is_under_dir`.

Types :

- `TrackItem` : `audio_path`, `image_path`, `output_filename` (basename `.mp4`).
- `BatchResult` : `successes`, `failures` (echecs d’encodage **et** pistes sans image assignee).

`batch_encode()` : construit des `TrackItem`, enchaine `encode_video()`, retourne `BatchResult`. Les echecs « pas d’image » sont enregistres dans `failures` sans tenter l’encodage.

### Gestion des erreurs

- `encode_video()` leve des exceptions (jamais `sys.exit`). Leve `NotADirectoryError` si le dossier parent du fichier de sortie existe en tant que fichier.
- `validate_inputs()` leve `FileNotFoundError` (absent) ou `ValueError` (dossier, extension invalide).
- `_prepare_image()` leve `ValueError` pour dimensions nulles. Les erreurs PIL (image corrompue) sont wrappees en `ValueError` par `encode_video()`.
- Si ffmpeg n'est pas installe : `RuntimeError`.
- `batch_encode()` leve `FileNotFoundError` / `NotADirectoryError` si le dossier d'entree est invalide ou si `--output-dir` pointe sur un fichier existant ; leve `ValueError` si deux pistes produiraient le **meme nom de sortie** ; leve `FileNotFoundError` si aucun job n'est possible (tracks vide ou toutes invalides en mode manifest, pas d'audio en mode scan). Si toutes les pistes echouent par manque d'image, retourne `BatchResult` avec `successes=[]` et `failures` rempli. Note : le mode scan ne re-scanne plus `idir` pour verifier la presence d'audio ; cette information est deja capturee par `_resolve_track_pairs`.
- La CLI (`cli.py`) catche ces exceptions et retourne un code de sortie (0 ou 1).

### Repertoire temporaire

`encode_video()` utilise `tempfile.mkdtemp()` pour le repertoire de travail (image preparee). Le repertoire est nettoye dans un bloc `finally` meme en cas d'erreur.

## Conventions

### Settings (`settings.py`)

- `QualityPreset` : TypedDict avec `resolution`, `video_bitrate`, `frame_rate`.
- `QUALITY_PRESETS` : dictionnaire de presets (`"1080p"`, `"4k"`).
- `ENCODING_SETTINGS` : parametres constants du codec (H.264 High, AAC 48kHz, yuv420p, faststart). Cles notables : `preset: "slow"` (encodage lent/haute qualite) et l'option ffmpeg `-tune stillimage` (optimisation pour image fixe). Modifier `preset` vers `"medium"` ou `"fast"` reduit le temps d'encodage au detriment du ratio qualite/taille.
- `SUPPORTED_*_EXTENSIONS` : sets d'extensions valides.

Pour ajouter une nouvelle qualite (ex. 1440p), ajouter une entree dans `QUALITY_PRESETS`.

### Encoder (`encoder.py`)

- `resolve_quality()` : retourne un `QualityPreset`. Leve `ValueError` si inconnu. La fonction est insensible a la casse (`"1080P"`, `"4K"` acceptes). Attention : la CLI utilise `argparse choices` qui est case-sensitive ; seuls `"1080p"` et `"4k"` sont acceptes en ligne de commande.
- `validate_inputs()` : utilise `is_file()` (rejette les dossiers, les symlinks cassés, les fichiers absents). Leve `FileNotFoundError` si absent, `ValueError` si c'est un dossier ou une extension non supportee.
- `_prepare_image(path, work_dir, resolution)` : retourne le chemin de l'image preparee. Si deja a la bonne taille, retourne le chemin original. Leve `ValueError` pour une image de dimensions nulles (`0×0`). Les erreurs PIL (`UnidentifiedImageError`, `OSError`) sont capturees dans `encode_video()` et converties en `ValueError("Cannot read image …")`.
- `encode_video()` : accepte `quality` (str) OU des overrides manuels (`resolution`, `video_bitrate`, `frame_rate`). Les overrides ont priorite sur le preset.
- `BatchResult` : dataclass avec `successes: list[Path]` et `failures: list[tuple[Path, str]]`.
- `batch_encode()` : s'appuie sur `_resolve_track_pairs()` (manifest, name-match, cover). Retourne un `BatchResult`. Leve `NotADirectoryError` si `input_dir` n'est pas un dossier ou si `output_dir` existe en tant que fichier. Leve `ValueError` sur noms de sortie dupliques. Leve `FileNotFoundError` si aucun job n'est possible. Un batch entierement sans piste valide retourne uniquement des echecs.
- `_resolve_track_pairs()` : retourne `(list[TrackItem], list[tuple[Path, str]], mode)` avec `mode` in `("manifest", "scan")`.
- `_normalize_output_name(name)` : ajoute `.mp4` au champ `output` du manifest si absent ou si l'extension n'est pas `.mp4`.

### CLI (`cli.py`)

- Sous-commandes : `single` et `batch`.
- `main()` retourne un int (0 = succes, 1 = erreur).
- `--resolution WxH`, `--bitrate`, `--fps` sont disponibles **uniquement en mode `single`**. Le mode `batch` n'expose que `-q`/`--quality`, `-o`/`--output-dir` (defaut : `<input_dir>/output`) et `--cover-name`.
- `_parse_resolution()` rejette les valeurs non positives (`0x1080`, `-1x1080` → `None`).
- En mode `batch`, retourne 1 si au moins un fichier a echoue.

### Tests

- `tests/conftest.py` : fixtures partagees (`tmp_image`, `tmp_audio`, `batch_dir`, `mock_ffmpeg_ok`, `mock_ffmpeg_fail`).
- **Tests fonctionnels manuels** (Luna, 2026-04-23) : validés en conditions réelles — `single` (1080p, 4k, custom resolution/bitrate), `batch` avec manifest (1 image/track, 3 tracks — couleurs vérifiées pixel par pixel), edge cases (path traversal bloqué, output dir = fichier existant, manifest racine = liste, silent skip audio inexistant, duplicate output names).

### Approbation

- **Luna** — testée et approuvée ✅ (23/04/2026)
- `tests/test_encoder.py` : tests unitaires sur validation, preparation image, encodage (ffmpeg mocke), batch, resultats partiels.
- `tests/test_cli.py` : tests du parsing CLI, `_parse_resolution`, retours de `main()` (single/batch/help, cas d'erreur).
- ffmpeg est toujours mocke dans les tests unitaires via `unittest.mock.patch`.

### Dependances

- `Pillow>=11.0` : manipulation d'images (resize, canvas, sauvegarde).
- `pytest>=8.0` : framework de test (dev dependency).
- `pyproject.toml` definit l'entry point `video-maker = "video_maker.cli:main"` (installable via `pip install -e .` ; commande `video-maker` disponible en PATH).

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
