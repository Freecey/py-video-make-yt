# Tasks done — Audit / Review Round 5 + docs completeness — 2026-04-23

## Aucune correction de code

Le code est propre. Aucun bug détecté.

## AGENTS.md — 6 lacunes comblées (focus completeness pour agents IA)

| # | Ligne | Lacune | Correction |
|---|-------|--------|-----------|
| 1 | CLI section | `-o`/`--output-dir` absent de la liste des flags batch | Ajouté : `-o`/`--output-dir` (defaut `<input_dir>/output`) |
| 2 | Settings | `ENCODING_SETTINGS` ne mentionnait pas `preset: "slow"` ni `-tune stillimage` | Ajout avec note de performance (`"medium"`/`"fast"` = plus rapide) |
| 3 | Gestion erreurs + Encoder | `batch_encode` lève `ValueError` sur noms de sortie dupliqués — non documenté | Ajouté aux deux sections (gestion erreurs + conventions encoder) |
| 4 | Mode batch | Fallback scan déclenché aussi quand `tracks` n'est pas une liste (pas seulement JSON invalide) | Point 3 du mode batch mis à jour |
| 5 | Encoder | `_normalize_output_name` non documenté (ajoute `.mp4` automatiquement) | Ajouté dans la section encoder |
| 6 | Dependances | Entry point `video-maker` dans `pyproject.toml` non mentionné | Ajouté dans la section dependances |

## docs/README.md — aucune modification nécessaire ✓

## Vérifié clean

- 55/55 tests passent
- 0 erreur lint

## Fix additionnel (post-audit)

| Fichier | Issue | Fix |
|---------|-------|-----|
| `encoder.py` | `output_dir` pointant sur un fichier existant → `FileExistsError` non catchée → traceback brut | Validation anticipée : `NotADirectoryError` si `output_dir.exists() and not output_dir.is_dir()` |
| `tests/test_encoder.py` | Cas non testé | `test_batch_encode_output_dir_is_existing_file` ajouté |
| `docs/AGENTS.md` | Comportement non documenté | Note ajoutée dans gestion des erreurs |

56/56 tests passent.
