# OIEC-STM-Agent Visual Matching

The Visual Workbench includes deterministic image-similarity and three-view matching commands. These operations are local analysis tools inside the Visual CLI; they do not grant repository mutation authority and they do not execute arbitrary shell commands.

Install the visual extra first:

```bash
pip install '.[visual]'
```

Visual matching uses Pillow for bounded raster preparation, edge extraction, and generated mesh projection images.

## Match methods

The matcher exposes the individual tests rather than hiding them behind a single opaque score.

### `mse`

Normalized mean-squared-error similarity. This is most sensitive to direct pixel differences after preprocessing.

```text
score = 1 - MSE / 255^2
```

It is useful when the two images have comparable framing and appearance, but is sensitive to translation, lighting, and rendering differences.

### `ncc`

Normalized cross-correlation of grayscale pixels. This measures whether spatial intensity variation rises and falls together after normalization.

It is less sensitive than direct MSE to a global brightness offset, but still depends strongly on spatial alignment.

### `ssim-global`

A bounded global structural-similarity calculation using luminance, variance, and covariance terms. It is deliberately named `ssim-global` because it is not the windowed SSIM algorithm provided by specialist image-processing libraries.

### `histogram`

Cosine similarity over a 64-bin grayscale histogram. It measures broad appearance distribution and is much less sensitive to pixel position.

A high histogram score does not prove geometric similarity.

### `edge-dice`

Dice overlap of thresholded image edges with a small tolerance dilation. This is primarily a shape/contour measure.

```text
Dice = 2 |A intersect B| / (|A| + |B|)
```

### `edge-chamfer`

A symmetric Chamfer-style edge-distance score. Each edge set is compared to a distance transform of the other edge set, then the two directed distances are averaged.

This is useful when contours are close but do not overlap pixel-for-pixel.

## Profiles

`method=all` calculates every metric and combines selected metrics with deterministic weights.

### `profile=appearance`

Emphasizes:

- MSE;
- NCC;
- global SSIM;
- histogram similarity.

Use it for two similarly framed raster images or renders where tone and appearance matter.

### `profile=shape`

Emphasizes:

- edge Dice;
- edge Chamfer;
- with smaller NCC/global-SSIM contributions.

Use it for matching photographs or drawings against wireframe/orthographic mesh projections.

### `profile=balanced`

Uses all six metrics with a more even weighting.

The profile is ignored when one explicit `method=...` is selected; the selected method itself becomes the reported score.

## Preprocessing

Three bounded preprocessing modes are available:

```text
preprocess=fit
preprocess=edge-fit
preprocess=stretch
```

`fit` preserves aspect ratio and centers the image on a square comparison canvas.

`edge-fit` first finds the structural edge extent, crops to that extent when valid, then aspect-fits the result. This is useful for object silhouettes with different margins.

`stretch` directly resizes both images to the square comparison size. It is useful only when intentional non-uniform scaling is acceptable.

The default comparison size is 256 pixels and the implementation caps comparison dimensions.

## Pair matching

```text
match IMG1 IMG2
```

Example:

```text
match @img:a1b2c3d4e5f60000 @img:ffeeddccbbaa0000 method=all profile=balanced
```

Single metric:

```text
match @img:a1b2c3d4e5f60000 @img:ffeeddccbbaa0000 method=edge-chamfer preprocess=edge-fit size=320
```

Every match produces a content-addressed JSON report:

```text
@match:<sha-prefix>
```

The report stores the preprocessing mode, selected profile, individual metric results, and final score in integer basis points from `0` to `10000`.

## Pairwise matching across many images

```text
match-matrix IMG1 IMG2 [IMG3 ... IMG12]
```

Example:

```text
match-matrix @img:aaa... @img:bbb... @img:ccc... method=all profile=shape
```

The CLI prints a compact similarity matrix and stores the complete pair reports in one `@match` asset.

This is useful for:

- finding near-duplicate reference images;
- grouping related views;
- comparing multiple candidate renders;
- finding which generated image is most similar to a reference.

## Mesh to front/top/side views

A registered OBJ/STL mesh can be deterministically projected into the same three coordinate planes used by the supervised 3D Bezier editor:

```text
Front: X/Z
Top:   X/Y
Side:  Y/Z
```

Generate the three views in the mesh's world coordinate frame:

```text
mesh-views @mesh:abc... orientation=world size=512
```

The three generated projections are registered as normal `@img` assets and a manifest is registered as `@match`.

### Camera-relative three views

The 3D viewer maintains an interactive yaw/pitch camera orientation. To treat the current viewer orientation as a temporary rotated coordinate frame before taking the three orthographic projections:

```text
mesh-views @mesh:abc... orientation=camera size=512
```

This does not create three perspective screenshots. Instead it rotates the mesh by the current viewer yaw/pitch and then produces orthographic X/Z, X/Y, and Y/Z projections from that rotated frame.

This is useful for converting an interactively chosen 3D orientation into a repeatable three-view reference set.

## Explicit mesh-to-three-image match

When the input images are already known to be front/top/side:

```text
match-3view MESH front=IMG top=IMG side=IMG
```

Example:

```text
match-3view @mesh:abc... \
  front=@img:111... \
  top=@img:222... \
  side=@img:333... \
  orientation=world \
  method=all \
  profile=shape \
  preprocess=edge-fit \
  size=256
```

The command returns:

- front similarity;
- top similarity;
- side similarity;
- mean aggregate three-view similarity;
- generated projection references;
- a content-addressed `@match` report.

Any individual metric can be used instead:

```text
match-3view @mesh:abc... front=@img:111... top=@img:222... side=@img:333... method=edge-chamfer
```

## Classifying arbitrary input views into front/top/side

`classify-3view` compares each supplied image against all three generated mesh projections.

```text
classify-3view MESH IMG1 [IMG2 ... IMG12]
```

Example with three camera renders in unknown order:

```text
classify-3view @mesh:abc... @img:camA... @img:camB... @img:camC... profile=shape
```

For three or more candidates, the classifier searches bounded one-to-one assignments and selects the combination that maximizes total front/top/side similarity. If more than three images are supplied, the best three are assigned and the remainder are reported as unassigned.

For one or two candidates, the classifier finds the best partial one-to-one assignment to the three canonical views.

The report contains the complete score table:

```text
candidate image -> front score
candidate image -> top score
candidate image -> side score
```

plus the chosen assignment and aggregate score.

A camera-relative classification can use the current 3D viewer orientation:

```text
classify-3view @mesh:abc... @img:a... @img:b... @img:c... orientation=camera
```

## Intended interpretation

Similarity scores are evidence about visual correspondence, not proof of object identity.

For example:

- a high histogram score can occur for geometrically unrelated images with similar tonal distributions;
- a high edge score can occur for different objects with similar silhouettes;
- a wireframe mesh and a photograph are expected to score poorly on raw pixel appearance but may score meaningfully on contour-oriented methods;
- occlusion, perspective, lens distortion, background clutter, and lighting can reduce scores even when the underlying object is the same.

For 3D reconstruction work, the most useful workflow is generally:

```text
input images
  -> classify likely front/top/side correspondence
  -> inspect individual metric scores
  -> choose/confirm three references
  -> run explicit match-3view
  -> edit 3D Bezier curves or model
  -> regenerate views
  -> repeat the match
```

This turns three-view fitting into a supervised evidence loop rather than a one-shot visual judgment.

## Current limits

- Mesh projection is orthographic wireframe, not hidden-line/silhouette rendering.
- No automatic camera calibration is performed yet.
- No perspective-square or vanishing-point recovery is performed in this matching layer yet.
- No learned embedding model is used; all current metrics are deterministic local algorithms.
- Comparison does not yet optimize translation/rotation/scale beyond the documented preprocessing modes.
- Camera-relative mode uses the current viewer yaw/pitch but not its perspective distance or zoom.

Useful next extensions are bounded 2D alignment search, silhouette extraction, perspective-camera calibration, learned embedding adapters with model/version provenance, and an IURM loop that proposes the next control-point change that most improves three-view fit.
