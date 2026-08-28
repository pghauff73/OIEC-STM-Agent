# OIEC-STM-Agent Visual Workbench

The Visual Workbench adds a supervised multimodal editing surface to the existing Tkinter engineering GUI. It is a center-pane tab alongside Agent Chat, OURD, IURM, Trace, and the semantic terminal.

## Capabilities

The first vertical slice provides:

- a bounded command line inside the GUI;
- image input from user-selected files;
- stable content-addressed image references such as `@img:3f24...`;
- multimodal provider expansion so a referenced image is attached to the current model request for compatible Responses API models;
- passive image display without extra dependencies for Tk-supported image types;
- richer supervised raster editing when Pillow is installed;
- OBJ and STL wireframe display with mouse orbit and zoom;
- stable `@mesh:...` references;
- a synchronized front/top/side cubic 3D Bezier editor;
- stable `@curve:...` references for accepted Bezier scenes;
- explicit Accept/Revert supervision for 2D image and 3D curve edits.

## Install raster editing support

The base GUI remains dependency-light. Install the optional visual extra for JPEG/WebP display and raster edits:

```bash
pip install -e '.[visual]'
```

This installs Pillow. The 3D wireframe viewer and Bezier editor use Tkinter and the Python standard library.

## Visual asset references

User-selected files are copied into the protected GUI bookkeeping area:

```text
.ourd-agent/gui-assets/
```

The index records filename, media type, content hash, size, and stored path. References are content-addressed:

```text
@img:<sha-prefix>
@mesh:<sha-prefix>
@curve:<sha-prefix>
```

Importing the same bytes twice yields the same reference.

The model does not receive arbitrary filesystem paths. An image is attached to a model request only when the user explicitly places its registered `@img:...` reference in the current chat message. Expansion to `input_image` occurs at the provider boundary, so base64 image data is not persisted in the ordinary chat transcript or OIEC trace events.

Whether a local OpenAI-compatible model can consume the image still depends on that model and endpoint supporting multimodal Responses input. Unsupported model/backend combinations fail at the provider boundary rather than silently pretending the pixels were inspected.

## Visual CLI

The Visual Workbench includes a local visual command line. It does not execute arbitrary shell commands.

```text
help
list [image|mesh|curve]
open-image [PATH]
open-mesh [PATH]
show REF
ref REF
image rotate DEG
image flip-h
image flip-v
image grayscale
image accept
image revert
image export
curve new [NAME]
curve accept
curve revert
curve export
curve import
mesh reset
chat TEXT...
```

`ref REF` inserts the selected reference into the Agent Chat composer. `chat TEXT...` submits a governed agent turn through the existing GUI controller.

## Supervised 2D image editing

Raster edits are non-destructive until explicitly accepted.

The editor supports:

- rotation;
- horizontal and vertical mirroring;
- grayscale conversion;
- brightness and contrast staging;
- drag-to-select cropping;
- Accept;
- Revert;
- explicit export of the accepted revision.

A typical cycle is:

```text
accepted image
  -> stage one or more edits
  -> inspect preview
  -> Accept OR Revert
```

Accepting a revision registers new bytes and therefore creates a new content-addressed `@img` reference. Revert restores the most recently accepted image.

## 3D object viewer

The initial viewer supports bounded wireframe loading of:

- OBJ;
- binary STL;
- ASCII STL.

Mesh parsing is bounded by maximum vertex/edge counts and rendering subsamples very large edge sets. The viewer supports mouse orbit, wheel zoom, and view reset. It is a display surface, not a mesh mutation engine in this milestone.

## Supervised three-view 3D Bezier editor

The Bezier editor represents cubic 3D curves with four control points:

```text
P0, P1, P2, P3 in R^3
```

It simultaneously projects each selected curve into:

```text
Front: X/Z
Top:   X/Y
Side:  Y/Z
```

Dragging a control point in any one projection updates the corresponding two coordinates of the same 3D point. The third coordinate remains unchanged, and all three projections redraw immediately.

The curve is evaluated as:

```text
B(t) = (1-t)^3 P0
     + 3(1-t)^2 t P1
     + 3(1-t)t^2 P2
     + t^3 P3
```

for `0 <= t <= 1`.

Curve changes are staged. `Accept Revision` commits the working scene as the new accepted scene and registers a new `@curve` asset. `Revert Revision` discards pending control-point/curve changes.

Accepted scenes use a small versioned JSON representation containing curve IDs, names, revision number, and four 3D control points per cubic curve.

## Governance boundary

The visual editors do not add a raw model mutation route into repository files.

- Visual imports are explicit user actions.
- Internal visual asset storage lives under `.ourd-agent/` bookkeeping.
- The local Visual CLI has no arbitrary shell execution.
- Model-visible images require explicit `@img` references.
- Editing changes are staged and supervised.
- Export is an explicit human file-dialog action.
- Existing EON/authority/evidence rules remain the mutation route for model-driven repository changes.

A later milestone can promote accepted image/curve revisions into formal EGCF ArtifactRecords and EON transactions when they need to become governed repository assets.

## Current limits

This first slice intentionally does not attempt to be Blender or a full raster painting program.

- 3D display is wireframe only.
- OBJ/STL are the initial mesh formats.
- Bezier editing currently uses cubic curves rather than surfaces or curve networks.
- 2D editing is a bounded transform/crop/tone stack, not brush painting or generative fill.
- Local multimodal inference depends on the selected Ollama/OpenAI-compatible model actually supporting image input.
- `@mesh` and `@curve` references are GUI/reference objects; only `@img` references are currently expanded into provider binary inputs.

These limits keep the milestone deterministic enough to test before adding texture painting, mesh editing, curve networks, surfaces, image-generation edit proposals, or Progen3D grammar binding.
