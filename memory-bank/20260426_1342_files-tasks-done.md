# Tasks done — 2026-04-26 13:42

## Nouvelle fonctionnalité — Fond flouté (`--no-blur-bg`)

### Comportement
- **Par défaut** : les zones vides (letterbox) sont remplies par la même image redimensionnée en mode "cover" + `GaussianBlur(radius=40)` — zéro bande noire visible
- **`--no-blur-bg`** : revient au comportement classique (fond noir), disponible en mode `single` et `batch`

### Algorithme (encoder.py `_prepare_image`)
1. **Fond flouté** : image → cover-scale (remplit tout le canvas, crop centré) → `GaussianBlur`
2. **Premier plan** : image → contain-scale (ratio préservé, centré) — logique inchangée
3. Coller le premier plan sur le fond

### Fichiers modifiés
- **`video_maker/settings.py`** : ajout de `BLUR_BACKGROUND_RADIUS = 40`
- **`video_maker/encoder.py`** :
  - Import `ImageFilter` de Pillow
  - Import `BLUR_BACKGROUND_RADIUS` de settings
  - `_prepare_image(…, blur_bg=True)` : algo cover+blur ou fond noir
  - `encode_video(…, blur_bg=True)` : transmet à `_prepare_image`
  - `batch_encode(…, blur_bg=True)` : transmet à `encode_video`
- **`video_maker/cli.py`** : `--no-blur-bg` (store_false → `blur_bg`) sur `single` et `batch`
- **`tests/test_encoder.py`** : 4 nouveaux tests (blur remplace noir, noir si False, taille exacte inchangée, propagation blur_bg=False)
- **`tests/test_cli.py`** : 3 nouveaux tests (défaut True, --no-blur-bg False, propagation vers _prepare_image)
- **`docs/AGENTS.md`** : flux de données, `_prepare_image`, `encode_video`, `batch_encode`, CLI, settings
- **`docs/README.md`** : section image + exemples --no-blur-bg
- **`README.md`** : features list + options table

### Tests
- **67/67 passed** (7 nouveaux tests ajoutés ce round)
