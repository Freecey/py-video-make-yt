# Tasks done — Audit / Review Round 3 — 2026-04-23

## Issues found and fixed

| # | File | Issue | Fix |
|---|------|-------|-----|
| 1 | `video_maker/` | `python -m video_maker` cassé : pas de `video_maker/__main__.py` | Créé `video_maker/__main__.py` qui appelle `main()` |
| 2 | `encoder.py` | `validate_inputs` utilisait `exists()` — un dossier nommé `x.jpg` passait sans erreur | Remplacé par `is_file()`, lève `ValueError` si c'est un dossier |
| 3 | `encoder.py` | `_prepare_image` pouvait produire des dimensions nulles avec des ratios extrêmes | Ajout d'un guard `max(1, ...)` + `ValueError` pour images `0×0` |
| 4 | `encoder.py` | `PIL.UnidentifiedImageError` / `OSError` dans `_prepare_image` non catchées → traceback brut | Wrapées dans `ValueError("Cannot read image …")` avant d'entrer dans le `try` ffmpeg |
| 5 | `encoder.py` | Paramètre `image_name: str` dans `_resolve_image_for_track` jamais utilisé (API morte) | Supprimé de la signature et des deux call-sites |
| 6 | `cli.py` | `_parse_resolution("0x1080")` retournait `(0, 1080)` passé tel quel à ffmpeg | Ajout `if w <= 0 or h <= 0: return None` |
| 7 | `README.md` | `.opus` absent de la liste des formats audio (présent dans `settings.py`) | Ajouté |

## Tests ajoutés (6 nouveaux)

| Test | Fichier | Couverture |
|------|---------|-----------|
| `test_resolve_quality_case_insensitive` | `test_encoder.py` | `"1080P"`, `"4K"` |
| `test_validate_inputs_image_is_directory` | `test_encoder.py` | image = dossier |
| `test_validate_inputs_audio_is_directory` | `test_encoder.py` | audio = dossier |
| `test_prepare_image_corrupt_raises` | `test_encoder.py` | image corrompue → `ValueError` |
| `test_prepare_image_zero_dimension_raises` | `test_encoder.py` | image `0×0` → `ValueError` |
| `test_parse_resolution_zero_or_negative` | `test_cli.py` | `0x1080`, `-1920x1080` → `None` |

## Vérifié clean

- 0 erreur de lint sur tous les fichiers `.py` modifiés
- 55/55 tests passent (+ 6 par rapport au round précédent)
- `python -m video_maker --help` fonctionne correctement
