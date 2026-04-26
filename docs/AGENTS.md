# AGENTS.md — Documentation technique pour agents IA

Ce document decrit l'architecture et les conventions du projet video-maker-auto pour faciliter l'intervention d'agents IA sur la base de code.

## Resume du projet

**Objectif** : Outil CLI Python qui combine une image fixe + un fichier audio en video MP4 optimisee pour YouTube via ffmpeg.

**Stack** : Python 3.10+, ffmpeg (subprocess.Popen), Pillow (redimensionnement image, miniatures), argparse (CLI), tomllib/tomli (config).

**Dependances** : Pillow (manipulation d'images), tomli (backport tomllib pour Python < 3.11). Aucun framework externe.

**Dev dependencies** : pytest, pytest-cov, ruff, mypy.

## Architecture

```
video_maker/
├── __init__.py      # Vide, marque le package
├── __main__.py      # Active `python -m video_maker` (appelle cli.main())
├── cli.py           # Point d'entree CLI, sous-commandes: single, batch
├── config.py        # Chargement config TOML (~/.video-maker.toml)
├── encoder.py       # Logique metier: validation, preparation image, encodage ffmpeg, batch
└── settings.py      # Presets qualite (1080p/4k), config encoding YouTube, constantes
```

### Flux de donnees

```
Image + Audio
  -> validate_inputs()        verification extensions et existence
  -> _prepare_image()         redimensionnement + letterboxing (Pillow)
                                blur_bg=True (defaut) : fond = image cover-scaled + GaussianBlur
                                blur_bg=False         : fond = noir (0,0,0)
  -> subprocess.Popen(ffmpeg) encodage H.264 + AAC en MP4 (streaming stderr pour progress)
  -> output.mp4
```

La commande ffmpeg utilise `-map 0:v:0 -map 1:a:0` pour lier l'image bouclee au flux video et **uniquement le premier flux audio** du fichier audio. Les fichiers M4A/MP3 avec pochette embarquee en flux MJPEG ne perturbent plus la selection de flux.

L'image est pretraitee par Pillow : redimensionnement + letterboxing avec fond floute (par defaut) ou fond noir (`--no-blur-bg`). Le filtre ffmpeg `-vf` n'est pas utilise pour le redimensionnement (traitement entierement cote Pillow).

### Normalisation audio

Option `--normalize` : ajoute `-af loudnorm=I=<TARGET_I>:TP=<TARGET_TP>:LRA=<TARGET_LRA>` a la commande ffmpeg. Parametres EBU R128 configures dans `settings.py` (`LOUDNORM_TARGET_I`, `LOUDNORM_TARGET_TP`, `LOUDNORM_TARGET_LRA`).

### Texte superpose (overlay)

Option `--title` : ajoute un filtre ffmpeg `drawtext` a la commande. Le texte est centre horizontalement, positionne a `TEXT_OVERLAY_Y_OFFSET` pixels du bas. Parametres (taille, couleur, bordure) dans `settings.py` (`TEXT_OVERLAY_*`). Les caracteres speciaux (guillemets, backslashes, apostrophes) sont echappes via `_escape_drawtext()`.

### Miniatures

Option `--thumbnail` : genere un JPEG `THUMBNAIL_SIZE` (1280x720) avec Pillow a cote de la video de sortie. Nom : `<output_stem>_thumbnail.jpg`.

### Mode batch

Fichier optionnel : `tracks.json` (nom defini par `TRACKS_MANIFEST_FILENAME` dans `settings.py`).

Encodage parallele via `concurrent.futures.ThreadPoolExecutor` avec parametre `-j/--jobs`. Barre de progression visuelle `[=====>    ] 45%` sur stderr pendant l'encodage. Resume final avec timing et taille par piste.

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
2. **Image par piste** (ordre de priorite) : `image` sur la piste, puis `default_cover`, puis image avec le **meme stem** que l'audio, puis `cover.*` (`--cover-name`, defaut `cover`).
3. **Sans manifest**, **JSON invalide**, **racine JSON n'est pas un objet** (ex. tableau), ou **`tracks` n'est pas une liste** : avertissement stderr, scan de tous les fichiers audio (tries), meme logique d'image sans le manifest.
4. **`tracks.json` present et dict valide, mais sans cle `tracks`** (ex. `{"default_cover": "cover.jpg"}`) : aucun avertissement, fallback silencieux vers scan. Le champ `default_cover` eventuel est ignore car le scan n'utilise pas le manifest. Mode retourne : `"scan"`.
5. **Securite** : les chemins du manifest sont resolus sous `input_dir` (pas d'`..` sortant du dossier) via `_file_in_input_dir` / `_is_under_dir`.

Types :

- `TrackItem` : dataclass avec `audio_path`, `image_path`, `output_filename` (basename `.mp4`).
- `TrackResult` : dataclass avec `name`, `status` (ok/fail), `elapsed` (secondes), `size_bytes`. Propriete `size_mb` pour l'affichage.
- `BatchResult` : dataclass avec `successes`, `failures`, `track_results` (liste de `TrackResult`).

`batch_encode()` : construit des `TrackItem`, utilise `ThreadPoolExecutor` si `max_workers > 1`, retourne `BatchResult`. Les echecs « pas d'image » sont enregistres dans `failures` sans tenter l'encodage.

### Gestion des erreurs

- `encode_video()` leve des exceptions (jamais `sys.exit`). Leve `NotADirectoryError` si le dossier parent du fichier de sortie existe en tant que fichier.
- `validate_inputs()` leve `FileNotFoundError` (absent) ou `ValueError` (dossier, extension invalide).
- `_prepare_image()` leve `ValueError` pour dimensions nulles. Les erreurs PIL (image corrompue) sont wrappees en `ValueError` par `encode_video()`.
- Si ffmpeg n'est pas installe : `RuntimeError` leve par `check_ffmpeg_available()` (cache via `lru_cache`).
- `batch_encode()` leve `FileNotFoundError` / `NotADirectoryError` si le dossier d'entree est invalide ou si `--output-dir` pointe sur un fichier existant ; leve `ValueError` si deux pistes produiraient le **meme nom de sortie** ; leve `FileNotFoundError` si aucun job n'est possible (tracks vide ou toutes invalides en mode manifest, pas d'audio en mode scan). Si toutes les pistes echouent par manque d'image, retourne `BatchResult` avec `successes=[]` et `failures` rempli. Note : le mode scan ne re-scanne plus `idir` pour verifier la presence d'audio ; cette information est deja capturee par `_resolve_track_pairs`.
- **Auto-retry** : en cas d'echec ffmpeg, `_encode_single_track()` retente automatiquement une fois avec le preset `ultrafast`. Si la deuxieme tentative echoue, la piste est marquee en echec.
- La CLI (`cli.py`) catche ces exceptions et retourne un code de sortie (0 ou 1).

### Repertoire temporaire

`encode_video()` utilise `tempfile.mkdtemp()` pour le repertoire de travail (image preparee). Le repertoire est nettoye dans un bloc `finally` meme en cas d'erreur.

## Conventions

### Settings (`settings.py`)

- `QualityPreset` : frozen dataclass avec `resolution`, `video_bitrate`, `frame_rate`.
- `EncodingSettings` : frozen dataclass avec les parametres codec (`video_codec`, `audio_codec`, `audio_bitrate`, `audio_sample_rate`, `audio_channels`, `profile`, `preset`, `pix_fmt`, `movflags`).
- `QUALITY_PRESETS` : dictionnaire de presets (`"1080p"`, `"4k"`).
- `ENCODING_SETTINGS` : instance unique de `EncodingSettings`. Cles notables : `preset: "slow"` (encodage lent/haute qualite) et l'option ffmpeg `-tune stillimage` (optimisation pour image fixe). Modifier `preset` vers `"medium"` ou `"fast"` reduit le temps d'encodage au detriment du ratio qualite/taille.
- `BLUR_BACKGROUND_RADIUS` : rayon du flou Gaussian applique au fond (`int`, defaut `40`).
- `SUPPORTED_*_EXTENSIONS` : sets d'extensions valides.
- Normalisation audio : `LOUDNORM_TARGET_I` (-14.0 LUFS), `LOUDNORM_TARGET_TP` (-1.0 dBTP), `LOUDNORM_TARGET_LRA` (11.0 LU).
- Texte overlay : `TEXT_OVERLAY_FONT_SIZE` (36), `TEXT_OVERLAY_FONT_COLOR` ("white"), `TEXT_OVERLAY_BORDER_COLOR` ("black"), `TEXT_OVERLAY_BORDER_WIDTH` (2), `TEXT_OVERLAY_Y_OFFSET` (50).
- Miniatures : `THUMBNAIL_SIZE` ((1280, 720)), `THUMBNAIL_SUFFIX` ("_thumbnail"), `THUMBNAIL_FORMAT` ("JPEG").
- Manifest batch : `TRACKS_MANIFEST_FILENAME` ("tracks.json").

Pour ajouter une nouvelle qualite (ex. 1440p), ajouter une entree dans `QUALITY_PRESETS`.

### Config (`config.py`)

- `UserConfig` : dataclass (mutable) avec champs optionnels : `quality`, `output_dir`, `blur_bg`, `normalize`, `title` (tous `| None`).
- `load_config(path)` : charge un fichier TOML. Supporte le format avec section `[video-maker]` et le format plat. Retourne un `UserConfig` avec `None` pour les champs absents. Invalide/illisible → `UserConfig()` vide (warning logge).
- Utilise `tomllib` (Python 3.11+) ou `tomli` en backport.

### Encoder (`encoder.py`)

- `check_ffmpeg_available()` : verifie ffmpeg installe + codecs requis (libx264, aac). Resultat cache via `lru_cache`. Leve `RuntimeError` si absent.
- `resolve_quality()` : retourne un `QualityPreset`. Leve `ValueError` si inconnu. Insensible a la casse (`"1080P"`, `"4K"` acceptes). Attention : la CLI utilise `argparse choices` qui est case-sensitive ; seuls `"1080p"` et `"4k"` sont acceptes en ligne de commande.
- `validate_inputs()` : utilise `is_file()` (rejette les dossiers, les symlinks casses, les fichiers absents). Leve `FileNotFoundError` si absent, `ValueError` si c'est un dossier ou une extension non supportee.
- `_prepare_image(path, work_dir, resolution, blur_bg=True)` : retourne le chemin de l'image preparee. Si deja a la bonne taille, retourne le chemin original sans modification. Sinon, applique un **contain** (ratio preserve, centree) sur un fond : floute si `blur_bg=True` (cover-scale + `GaussianBlur(radius=BLUR_BACKGROUND_RADIUS)`), noir si `blur_bg=False`. Leve `ValueError` pour dimensions nulles (`0x0`). Les erreurs PIL (`UnidentifiedImageError`, `OSError`) sont capturees dans `encode_video()` et converties en `ValueError("Cannot read image ...")`.
- `encode_video()` : accepte `quality` (str) OU des overrides manuels (`resolution`, `video_bitrate`, `frame_rate`). Les overrides ont priorite sur le preset. Parametres : `blur_bg`, `dry_run`, `normalize`, `title`, `generate_thumbnail`, `_preset_override` (interne, pour retry).
- `batch_encode()` : s'appuie sur `_resolve_track_pairs()`. Retourne un `BatchResult`. Encodage parallele via `ThreadPoolExecutor` si `max_workers > 1`. Verification espace disque avant encodage. Barre de progression + resume final.
- `_encode_single_track()` : helper pour batch. Gere `skip_existing`, `dry_run`, retry avec preset ultrafast, timing (`time.monotonic()`), retourne `(output_path | None, thumbnail_info | None, TrackResult)`.
- `_resolve_track_pairs()` : retourne `(list[TrackItem], list[tuple[Path, str]], mode)` avec `mode` in `("manifest", "scan")`.
- `_escape_drawtext()` : echappe les caracteres speciaux pour le filtre ffmpeg `drawtext` (guillemets, backslashes, apostrophes).
- `_format_progress_bar()` : genere la barre visuelle `[=====>    ] XX%`.
- `_estimate_batch_size()` : estime l'espace disque necessaire pour un batch.
- `_print_batch_summary()` : affiche le tableau recapitulatif par piste.
- `_normalize_output_name(name)` : ajoute `.mp4` au champ `output` du manifest si absent ou si l'extension n'est pas `.mp4`.
- `_get_audio_duration()` : extrait la duree audio via `ffprobe`.
- `_parse_time_to_seconds()` / `_format_seconds()` : helpers pour le parsing de progression ffmpeg.
- `_parse_ffmpeg_error()` : extrait les messages d'erreur pertinents du stderr ffmpeg.

### CLI (`cli.py`)

- Sous-commandes : `single` et `batch`.
- `main()` retourne un int (0 = succes, 1 = erreur).
- Charge la config via `load_config(args.config)` et l'applique comme defaults (CLI flags ont toujours priorite).
- Application config :
  - `blur_bg` : argparse default True (store_false pour --no-blur-bg). Override depuis config seulement si config.blur_bg is not None et user n'a pas explicitement utilise --no-blur-bg.
  - `normalize` : `args.normalize or config.normalize or False`.
  - `title` : `args.title or config.title`.
  - `output_dir` (batch) : `args.output_dir` > `config.output_dir` > `<input_dir>/output`.
- `--resolution WxH`, `--bitrate`, `--fps` sont disponibles **uniquement en mode `single`**.
- `--no-blur-bg` : disponible dans les deux modes. Desactive le fond floute.
- `--normalize` : active la normalisation audio EBU R128.
- `--title` : texte superpose (drawtext).
- `--thumbnail` : genere une miniature JPEG.
- `--skip-existing` (batch) : ignore les fichiers deja encodes.
- `-j/--jobs` (batch) : nombre de workers d'encodage parallele.
- `--dry-run` (global) : affiche les commandes sans executer ffmpeg.
- `_parse_resolution()` rejette les valeurs non positives (`0x1080`, `-1x1080` → `None`).
- En mode `batch`, retourne 1 si au moins un fichier a echoue.

### Tests

- `tests/conftest.py` : fixtures partagees (`tmp_image`, `tmp_audio`, `batch_dir`) + autouse fixtures (`mock_get_audio_duration`, `mock_check_ffmpeg`).
- `tests/test_encoder.py` : ~95 tests unitaires couvrant validation, preparation image, encodage (ffmpeg mocke via `subprocess.Popen`), batch, normalisation, texte overlay, miniatures, retry, progres, resume, espace disque.
- `tests/test_cli.py` : ~27 tests du parsing CLI, `_parse_resolution`, retours de `main()` (single/batch/help, cas d'erreur, flags).
- `tests/test_config.py` : 9 tests — chargement TOML (fichier manquant, valide, invalide, chemin custom, format plat), application config (normalize, title, blur_bg), override CLI vs config.
- `tests/test_integration.py` : 3 tests d'integration avec vrai ffmpeg (marque `@pytest.mark.integration`).
- **Total** : ~117 tests unitaires + 3 integration, coverage ~90%.
- ffmpeg est toujours mocke dans les tests unitaires via `unittest.mock.patch`.
- `pytest.ini` (pyproject.toml) : `addopts = "-m 'not integration'"` — les tests integration ne tournent pas par defaut.
- Coverage threshold : 80% (CI et `make test-cov`).

**Tests fonctionnels manuels** (Luna, 2026-04-23) : valides en conditions reelles — `single` (1080p, 4k, custom resolution/bitrate), `batch` avec manifest (1 image/track, 3 tracks), edge cases (path traversal, output dir = fichier, manifest racine = liste, silent skip audio inexistant, duplicate output names).

### Approbation

- **Luna** — testee et approuvee (23/04/2026)

### Dependances

- `Pillow>=11.0` : manipulation d'images (resize, canvas, blur, sauvegarde, miniatures).
- `tomli>=2.0` : backport tomllib pour Python 3.10 (devient no-op sur 3.11+).
- `pytest>=8.0` : framework de test.
- `pytest-cov>=5.0` : couverture de code.
- `ruff>=0.8` : linter/formatter.
- `mypy>=1.0` : verification de types.
- `pyproject.toml` definit l'entry point `video-maker = "video_maker.cli:main"` (installable via `pip install -e .` ; commande `video-maker` disponible en PATH).

## Points d'extension connus

1. **Nouvelle qualite** : ajouter dans `QUALITY_PRESETS` dans `settings.py`.
2. **Ken Burns / zoom lent** : ajouter un filtre ffmpeg `-vf zoompan` dans `encoder.py`.
3. **Watermark** : ajouter un deuxieme input image et un filtre `overlay`.
4. **Autres formats de sortie** : ajouter le codec/container dans `settings.py` et une option CLI.

Note : l'overlay texte (`drawtext`) et la barre de progression sont deja implantes. La parallelisation batch via `ThreadPoolExecutor` est egalement en place.

## Commandes utiles

```bash
# Installer
python3 -m venv .venv && source .venv/bin/activate && pip install -e .

# Installer avec dev dependencies
pip install -e ".[dev]"

# Linter
ruff check .

# Verification de types
mypy video_maker/ --ignore-missing-imports

# Lancer les tests unitaires
python -m pytest tests/ -v

# Lancer les tests d'integration (necessite ffmpeg)
python -m pytest tests/ -m integration -v

# Coverage report (seuil 80%)
make test-cov

# Tout lancer (lint + typecheck + tests)
make all

# Utilisation single
python -m video_maker single -i cover.jpg -a song.mp3 -q 4k

# Utilisation batch
python -m video_maker batch /music/album -q 1080p

# Dry-run
python -m video_maker --dry-run batch /music/album
```
