# Visual CLI Mesh Import

The OIEC-STM Visual CLI accepts bounded mesh inputs through the existing `open-mesh` command:

```text
open-mesh /path/to/model.obj
open-mesh /path/to/model.stl
open-mesh /path/to/model.ply
```

Imported meshes receive a content-addressed `@mesh:<sha-prefix>` identity and are copied under the protected `.ourd-agent/gui-assets/` visual bookkeeping area.

## Supported formats

### Wavefront OBJ

OBJ is text/ASCII. The importer preserves:

- geometric vertices (`v`);
- polygon faces (`f`);
- texture coordinates (`vt`);
- negative OBJ indices;
- material assignment (`usemtl`);
- material libraries (`mtllib`);
- diffuse material color (`Kd`);
- opacity from `d` / `Tr`;
- diffuse texture maps (`map_Kd`);
- commonly used per-vertex RGB/RGBA extensions on `v` records.

Referenced MTL and texture files are copied into a content-addressed mesh bundle so relative paths continue to resolve after import. Every successfully resolved diffuse texture also receives a separate `@img:...` visual asset reference.

Texture-map options are preserved only insofar as the filename can be resolved. The first milestone does not reproduce every historical Wavefront map transform option in the Tk software viewer.

### STL

Both ASCII STL and standard binary little-endian STL are accepted.

The format is treated as triangle geometry. STL does not define standard UV coordinates, material libraries, or image texture mapping. If the 16-bit binary facet attribute field is nonzero, the importer reports this rather than silently interpreting one of the incompatible vendor-specific color conventions.

### PLY

PLY 1.0 is accepted in:

```text
ascii
binary_little_endian
binary_big_endian
```

The parser follows the typed PLY header rather than assuming a fixed vertex layout. It supports scalar and list properties using the standard PLY scalar types.

Recognized geometry and appearance properties include:

- `x`, `y`, `z` vertex positions;
- face `vertex_indices`, `vertex_index`, or `vertices` lists;
- vertex colors `red/green/blue[/alpha]` or `r/g/b[/a]`;
- vertex UV aliases `u/v`, `s/t`, `texture_u/texture_v`, `texcoord_u/texcoord_v`;
- per-face `texcoord`, `texcoords`, or `texture_coordinates` lists;
- common face material/texture indices;
- optional PLY material elements with diffuse RGB fields;
- common external texture extensions expressed as `comment TextureFile <file>` or `texture_file` (including `obj_info`).

Core PLY supports texture coordinates but does not standardize texture-image descriptions. External `TextureFile` handling is therefore explicitly treated as an interoperability extension rather than a core PLY guarantee.

## Texture and color display

The Tk 3D viewer now reports:

```text
format + encoding
vertex / face / edge counts
UV count
material count
texture count
UV-mapped yes/no
vertex-color yes/no
```

It can display bounded flat surfaces using material diffuse colors or vertex colors, overlaid with the wireframe. If a texture image is present and Pillow is installed, the viewer shows the imported texture map as a preview and reports whether usable UV mapping was preserved.

Install visual support with:

```bash
pip install -e '.[visual]'
```

The current Tk viewer deliberately does **not** claim full UV texture rasterization onto perspective polygons. The importer preserves the UV/material/texture data so a later OpenGL/Progen3D renderer can consume the same mesh bundle without reparsing or losing provenance.

## Bounded import behavior

The importer limits active mesh size to bounded vertex, face, edge, and PLY-list counts. Dependencies are resolved conservatively inside the selected mesh directory tree and missing or escaping dependencies are reported as warnings rather than guessed.

A mesh bundle is structured conceptually as:

```text
.ourd-agent/gui-assets/
  mesh-bundles/
    <mesh-sha256>/
      model.obj | model.ply | model.stl
      materials.mtl
      texture.png
      ...
```

Texture files also appear in the visual registry as independent `@img:` assets.

## Relationship to matching and three-view work

Imported OBJ, STL, and PLY meshes all flow through the same `MeshData` representation, so existing visual matching commands continue to work:

```text
mesh-views @mesh:... orientation=world
mesh-views @mesh:... orientation=camera
match-3view @mesh:... front=@img:... top=@img:... side=@img:...
classify-3view @mesh:... @img:... @img:... @img:...
```

The three-view matcher currently compares deterministic geometric projections. Texture-aware image matching can be layered on top later without changing mesh identity or the parsed UV/material state.
