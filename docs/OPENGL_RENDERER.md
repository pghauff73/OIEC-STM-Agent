# OIEC-STM OpenGL Renderer

This module adds an optional headless OpenGL 3.3 rendering backend to the Visual Workbench while keeping the imported `MeshData` representation renderer-neutral.

## Install

```bash
pip install '.[opengl]'
```

The OpenGL extra installs ModernGL with its headless context support plus Pillow for texture decode and framebuffer encoding. The ordinary GUI still works without this extra and keeps the existing Tk software mesh viewer as a fallback.

## Architecture

```text
OBJ / STL / PLY
      |
      v
  MeshData
      |
      v
compile_mesh()
      |
      +-- deterministic polygon triangulation
      +-- generated smooth normals
      +-- UV/material seam vertex expansion
      +-- material draw batches
      |
      v
 CompiledMesh
      |
      v
single-thread OpenGLRenderService
      |
      +-- ModernGL 3.3 standalone context
      +-- VBO / EBO / VAO upload
      +-- texture cache by content hash
      +-- depth framebuffer
      +-- fixed checked-in GLSL shaders
      |
      v
 RenderFrame
      |
      +-- GUI image preview
      +-- @img capture
      +-- three-view comparison
```

The model does not supply GLSL. Shader source is fixed in the repository and imported visual data is treated as data only.

## GPU mesh compilation

Imported polygons are converted to triangles before upload. The compiler projects a polygon into its dominant 2D plane and uses deterministic ear clipping. Degenerate or otherwise unresolved polygons fall back to a deterministic triangle fan and emit a warning.

OBJ-style split indexing is handled by expanding each GPU vertex using the corner identity:

```text
(position_index, uv_index, material_index)
```

This means one spatial position used by two different UV coordinates becomes two GPU vertices, preserving texture seams.

Each GPU vertex currently uses an interleaved 48-byte layout:

```text
position  vec3 float32
normal    vec3 float32
uv        vec2 float32
color     vec4 float32
```

Triangles are grouped into material-specific indexed draw batches.

## Normals

When imported normals are not available through the current mesh contract, the compiler generates smooth vertex normals by accumulating face normals over each source spatial vertex and normalizing the result. A later importer extension can add explicit normal indices and OBJ smoothing-group preservation without changing the renderer interface.

## Materials and textures

The v1 renderer maps existing imported material data as follows:

```text
MeshMaterial.diffuse         -> u_base_color
MeshMaterial.diffuse_texture -> sampler2D
vertex color                 -> vertex color attribute
```

Texture files are decoded through Pillow, vertically flipped for OpenGL texture coordinates, uploaded as RGBA8, mipmapped, and cached by SHA-256 of the texture bytes.

The renderer does not execute shaders or scripts from imported meshes.

## Context ownership

All OpenGL work occurs on one daemon renderer thread through `OpenGLRenderService`. Tk callbacks submit bounded synchronous requests to that thread. The OpenGL context is therefore created, used, and destroyed on the same thread.

Context initialization requests OpenGL 3.3. On Linux it first tries the ModernGL EGL headless backend, then the platform default standalone backend. Failure does not disable the rest of the Visual Workbench.

## Visual CLI

Inspect the GPU/backend:

```text
gl-info
```

Render the current model:

```text
render @mesh:... mode=textured view=perspective size=768
```

Supported modes:

```text
textured
material
vertex-color
wireframe
silhouette
normal
depth
```

Supported views:

```text
perspective
front
top
side
```

Generate canonical three views:

```text
render-3view @mesh:... mode=textured size=512 orientation=world
```

or rotate the mesh by the current software-viewer yaw/pitch before taking canonical orthographic views:

```text
render-3view @mesh:... mode=silhouette size=512 orientation=camera
```

Each render is registered as an ordinary content-addressed `@img:` visual asset. Three-view rendering also creates an `@match:` JSON report containing the exact mesh reference, render mode, orientation, camera rotation, generated image references, and OpenGL capability metadata.

## Render modes

### Textured

Material diffuse color, optional vertex color, and `map_Kd`/resolved base texture are combined and passed through simple directional lighting.

### Material

Shows imported diffuse material colors without texture sampling.

### Vertex color

Shows imported PLY/OBJ vertex colors multiplied by the default material color.

### Wireframe

Uses OpenGL polygon wireframe mode with depth testing.

### Silhouette

Outputs white visible mesh fragments. Canonical three-view silhouette renders use a black background and are intended for shape matching.

### Normal

Encodes normalized surface normals into RGB as:

```text
color = normal * 0.5 + 0.5
```

### Depth

Encodes framebuffer depth into grayscale. This first version uses `gl_FragCoord.z` and is therefore a normalized device-depth visualization rather than linear metric distance.

## Three-view conventions

The canonical orthographic views retain the existing Visual Workbench conventions:

```text
front : X / Z
 top  : X / Y
 side : Y / Z
```

The resulting `@img:` assets can be passed directly to `match`, `match-matrix`, or compared with reference imagery using the existing similarity tools.

## Bounds

The OpenGL compiler and renderer impose independent limits even though the mesh importer is already bounded:

```text
expanded GPU vertices <= 1,000,000
triangles             <= 2,000,000
framebuffer side      <= 4,096
```

Texture dimensions are additionally checked against `GL_MAX_TEXTURE_SIZE` reported by the active context.

## Validation

CPU-only tests validate triangulation, UV seam expansion, material batching, and generated normals.

An optional headless GPU smoke test runs only when ModernGL and Pillow are installed. If dependencies exist but the machine cannot create a usable headless OpenGL context, the test is skipped with the exact context failure rather than failing the base test suite.

## Current limits

This vertical slice intentionally stops before the later strategy milestones:

- imported explicit normal indices and OBJ smoothing groups are not yet preserved;
- no face/object ID picking framebuffer yet;
- no transparent-material sorting yet;
- no PBR material model;
- no native embedded OpenGL child window;
- OpenGL rendering is currently capture-oriented rather than a continuous 60 FPS Tk presentation loop;
- the existing `mesh-views` matching command still uses its deterministic software projection unless the user explicitly runs `render-3view` and compares the resulting `@img` assets.

These limits preserve a narrow, testable GL-0 through GL-3 implementation before adding picking, native presentation, or automatic OpenGL-backed fitting loops.
