# Tasks done — Audit / Review Round 7 — 2026-04-23

## Problèmes trouvés et corrigés

| # | Fichier | Problème | Fix |
|---|---------|----------|-----|
| 1 | `encoder.py` | Guard `output_path.parent` placé APRÈS `tempfile.mkdtemp()` et `_prepare_image()` — temp dir et image préparée créés inutilement avant de lever `NotADirectoryError` | Guard déplacé AVANT `work_dir` création (toute validation avant tout effet de bord) |
| 2 | `encoder.py` | `_load_tracks_manifest` retournait `None` silencieusement si le JSON est valide mais pas un objet dict (ex. `[...]`) — incohérent avec les autres cas de fallback | Ajout d'un warning stderr, cohérent avec "JSON invalide" et "`tracks` n'est pas une liste" |

## Tests ajoutés (+1, total 59)

| Test | Fichier | Couverture |
|------|---------|-----------|
| `test_resolve_track_pairs_non_dict_json_falls_back_to_scan` | `test_encoder.py` | `tracks.json` = tableau JSON valide → warning + fallback scan |

## AGENTS.md — 1 correction

Point 3 du mode batch mis à jour : ajout de "racine JSON n'est pas un objet" comme déclencheur de fallback (en plus de JSON invalide et `tracks` non-liste).

## docs/README.md — aucune modification nécessaire ✓

## Vérifié clean

- 59/59 tests passent
- 0 erreur lint
- docs cohérents avec le code
