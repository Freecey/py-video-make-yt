# Tasks done — Audit / Review Round 4 + verification docs — 2026-04-23

## Ecarts code vs docs trouves et corriges

| # | Fichier | Probleme | Fix |
|---|---------|----------|-----|
| 1 | `cli.py` | Message d'erreur pour resolution invalide disait "WxH format" meme pour `0x1080` (format OK, valeur invalide) | Message mis a jour : "WxH format with positive values" |
| 2 | `docs/AGENTS.md` | `resolve_quality` note "insensible a la casse" sans qualifier que le CLI impose lowercase via `choices` | Ajout de la precision : seuls `"1080p"` / `"4k"` acceptes en ligne de commande |
| 3 | `docs/AGENTS.md` | `--resolution`, `--bitrate`, `--fps` decrits sans indiquer qu'ils sont `single`-only | Section CLI mise a jour avec mention explicite |
| 4 | `docs/AGENTS.md` | Skip silencieux des entrees manifest avec audio absent/invalide non documente | Ajout d'une note dans la description du mode manifest |

## Verifie propre

- 0 lint error
- 55/55 tests passent
- `docs/README.md` : aucune modification necessaire (deja correct)
- `README.md` (racine) : aucune modification necessaire (deja correct)
