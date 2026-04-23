# Tasks done — Audit / Review Round 6 — 2026-04-23

## Bug trouvé et corrigé

| # | Fichier | Problème | Fix |
|---|---------|----------|-----|
| 1 | `encoder.py` | `encode_video()` : si le dossier parent du fichier de sortie est un fichier existant, `output_path.parent.mkdir()` lève `FileExistsError` non catchée → traceback brut en mode `single` (symétrique au fix batch du round précédent) | Guard ajouté avant `mkdir` : `NotADirectoryError` si `output_path.parent.exists() and not is_dir()` |
| 2 | `cli.py` | `main()` mode `single` ne catchait pas `NotADirectoryError` | Ajout de `NotADirectoryError` dans l'`except` du mode single |

## Tests ajoutés (+2, total 58)

| Test | Fichier |
|------|---------|
| `test_encode_video_output_parent_is_file` | `test_encoder.py` |
| `test_main_single_output_parent_is_file` | `test_cli.py` |

## AGENTS.md — 2 alignements

| Section | Avant | Après |
|---------|-------|-------|
| Gestion des erreurs / `encode_video` | "leve des exceptions" | + mention `NotADirectoryError` pour parent-as-file |
| Encoder / `batch_encode` | manquait `NotADirectoryError` pour `output_dir` | Aligné sur la section Gestion des erreurs |

## docs/README.md — aucune modification nécessaire ✓

## Vérifié clean

- 58/58 tests passent
- 0 erreur lint
- docs cohérents avec le code
