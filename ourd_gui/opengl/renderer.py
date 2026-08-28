from __future__ import annotations

import hashlib
import io
import math
import os
import struct
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ..mesh_formats import MeshData
from .math3d import RenderCamera, mat_mul, normalization_matrix, rotation_x, rotation_z
from .mesh_compile import CompiledMesh, compile_mesh

MAX_FRAMEBUFFER_SIDE = 4096
RENDER_MODES = {
    "textured": 0,
    "material": 1,
    "vertex-color": 2,
    "silhouette": 3,
    "normal": 4,
    "depth": 5,
    "wireframe": 6,
}

VERTEX_SHADER = """
#version 330 core
in vec3 in_position;
in vec3 in_normal;
in vec2 in_uv;
in vec4 in_color;

uniform mat4 u_model;
uniform mat4 u_view;
uniform mat4 u_projection;

out vec3 v_normal;
out vec2 v_uv;
out vec4 v_color;

void main() {
    vec4 world = u_model * vec4(in_position, 1.0);
    mat3 normal_matrix = mat3(transpose(inverse(u_model)));
    v_normal = normalize(normal_matrix * in_normal);
    v_uv = in_uv;
    v_color = in_color;
    gl_Position = u_projection * u_view * world;
}
"""

FRAGMENT_SHADER = """
#version 330 core
uniform sampler2D u_texture;
uniform vec4 u_base_color;
uniform int u_has_texture;
uniform int u_has_vertex_color;
uniform int u_mode;
uniform vec3 u_light_dir;

in vec3 v_normal;
in vec2 v_uv;
in vec4 v_color;
out vec4 frag_color;

void main() {
    if (u_mode == 3) {
        frag_color = vec4(1.0);
        return;
    }
    if (u_mode == 4) {
        frag_color = vec4(normalize(v_normal) * 0.5 + 0.5, 1.0);
        return;
    }
    if (u_mode == 5) {
        float d = clamp(gl_FragCoord.z, 0.0, 1.0);
        frag_color = vec4(vec3(d), 1.0);
        return;
    }

    vec4 color = u_base_color;
    if (u_mode == 2 && u_has_vertex_color != 0) {
        color *= v_color;
    } else if ((u_mode == 0 || u_mode == 6) && u_has_vertex_color != 0) {
        color *= v_color;
    }
    if (u_mode == 0 && u_has_texture != 0) {
        color *= texture(u_texture, v_uv);
    }
    float diffuse = max(dot(normalize(v_normal), normalize(-u_light_dir)), 0.0);
    float lighting = 0.28 + 0.72 * diffuse;
    frag_color = vec4(color.rgb * lighting, color.a);
}
"""


class OpenGLUnavailable(RuntimeError):
    pass


@dataclass(frozen=True)
class OpenGLCapabilities:
    backend: str
    version_code: int
    vendor: str
    renderer: str
    version: str
    glsl_version: str
    max_texture_size: int
    max_texture_units: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "backend": self.backend,
            "version_code": self.version_code,
            "vendor": self.vendor,
            "renderer": self.renderer,
            "version": self.version,
            "glsl_version": self.glsl_version,
            "max_texture_size": self.max_texture_size,
            "max_texture_units": self.max_texture_units,
        }


@dataclass(frozen=True)
class RenderFrame:
    width: int
    height: int
    rgba: bytes
    mode: str
    view: str
    backend: str

    def to_png_bytes(self) -> bytes:
        try:
            from PIL import Image
        except ImportError as exc:  # pragma: no cover - optional dependency
            raise OpenGLUnavailable("Pillow is required to encode OpenGL render captures") from exc
        image = Image.frombytes("RGBA", (self.width, self.height), self.rgba)
        buffer = io.BytesIO()
        image.save(buffer, format="PNG")
        return buffer.getvalue()


@dataclass
class _GPUTexture:
    texture: Any
    digest: str


@dataclass
class _GPUBatch:
    material_index: int
    index_buffer: Any
    vertex_array: Any


@dataclass
class _GPUMesh:
    compiled: CompiledMesh
    vertex_buffer: Any
    batches: list[_GPUBatch]

    def release(self) -> None:
        for batch in self.batches:
            try:
                batch.vertex_array.release()
            except Exception:
                pass
            try:
                batch.index_buffer.release()
            except Exception:
                pass
        try:
            self.vertex_buffer.release()
        except Exception:
            pass


class OpenGLRenderer:
    """Headless ModernGL renderer owned by a single thread."""

    def __init__(self, *, backend: str = "") -> None:
        try:
            import moderngl
        except ImportError as exc:
            raise OpenGLUnavailable(
                "ModernGL is not installed; install with `pip install -e '.[opengl]'`"
            ) from exc
        self.moderngl = moderngl
        requested = backend.strip() or os.getenv("OURD_GL_BACKEND", "").strip()
        attempts = [requested] if requested else ["egl", ""]
        errors: list[str] = []
        context = None
        selected_backend = ""
        for candidate in attempts:
            try:
                kwargs: dict[str, Any] = {"standalone": True, "require": 330}
                if candidate:
                    kwargs["backend"] = candidate
                context = moderngl.create_context(**kwargs)
                selected_backend = candidate or "default"
                break
            except Exception as exc:
                errors.append(f"{candidate or 'default'}: {type(exc).__name__}: {exc}")
        if context is None:
            raise OpenGLUnavailable("cannot create OpenGL 3.3 context: " + " | ".join(errors))
        self.ctx = context
        self.backend = selected_backend
        try:
            self.program = self.ctx.program(
                vertex_shader=VERTEX_SHADER,
                fragment_shader=FRAGMENT_SHADER,
            )
        except Exception as exc:
            raise OpenGLUnavailable(f"OpenGL shader compilation failed: {exc}") from exc
        self._mesh_cache: dict[str, _GPUMesh] = {}
        self._texture_cache: dict[str, _GPUTexture] = {}
        self._white_texture = self.ctx.texture((1, 1), 4, b"\xff\xff\xff\xff", alignment=1)
        self._white_texture.filter = (moderngl.NEAREST, moderngl.NEAREST)

    def capabilities(self) -> OpenGLCapabilities:
        info = dict(getattr(self.ctx, "info", {}) or {})
        return OpenGLCapabilities(
            backend=self.backend,
            version_code=int(getattr(self.ctx, "version_code", 0)),
            vendor=str(info.get("GL_VENDOR", "unknown")),
            renderer=str(info.get("GL_RENDERER", "unknown")),
            version=str(info.get("GL_VERSION", "unknown")),
            glsl_version=str(info.get("GL_SHADING_LANGUAGE_VERSION", "unknown")),
            max_texture_size=int(info.get("GL_MAX_TEXTURE_SIZE", 0) or 0),
            max_texture_units=int(info.get("GL_MAX_TEXTURE_IMAGE_UNITS", 0) or 0),
        )

    def close(self) -> None:
        for mesh in self._mesh_cache.values():
            mesh.release()
        self._mesh_cache.clear()
        for texture in self._texture_cache.values():
            try:
                texture.texture.release()
            except Exception:
                pass
        self._texture_cache.clear()
        try:
            self._white_texture.release()
        except Exception:
            pass
        try:
            self.program.release()
        except Exception:
            pass
        try:
            self.ctx.release()
        except Exception:
            pass

    def _gpu_mesh(self, mesh: MeshData, cache_key: str) -> _GPUMesh:
        cached = self._mesh_cache.get(cache_key)
        if cached is not None:
            return cached
        compiled = compile_mesh(mesh)
        vertex_buffer = self.ctx.buffer(compiled.vertex_bytes())
        batches: list[_GPUBatch] = []
        for batch in compiled.batches:
            index_data = struct.pack(f"<{len(batch.indices)}I", *batch.indices)
            index_buffer = self.ctx.buffer(index_data)
            vao = self.ctx.vertex_array(
                self.program,
                [
                    (
                        vertex_buffer,
                        "3f 3f 2f 4f",
                        "in_position",
                        "in_normal",
                        "in_uv",
                        "in_color",
                    )
                ],
                index_buffer=index_buffer,
                index_element_size=4,
            )
            batches.append(_GPUBatch(batch.material_index, index_buffer, vao))
        gpu = _GPUMesh(compiled, vertex_buffer, batches)
        self._mesh_cache[cache_key] = gpu
        return gpu

    def _texture(self, path_text: str):
        if not path_text:
            return self._white_texture
        path = Path(path_text)
        if not path.is_file():
            return self._white_texture
        content = path.read_bytes()
        digest = hashlib.sha256(content).hexdigest()
        cached = self._texture_cache.get(digest)
        if cached is not None:
            return cached.texture
        try:
            from PIL import Image
        except ImportError as exc:  # pragma: no cover - optional dependency
            raise OpenGLUnavailable("Pillow is required for textured OpenGL rendering") from exc
        try:
            with Image.open(path) as source:
                source.load()
                image = source.convert("RGBA").transpose(Image.Transpose.FLIP_TOP_BOTTOM)
        except OSError as exc:
            raise OpenGLUnavailable(f"cannot decode texture {path}: {exc}") from exc
        max_size = self.capabilities().max_texture_size
        if max_size and (image.width > max_size or image.height > max_size):
            raise OpenGLUnavailable(
                f"texture {path.name} exceeds GL_MAX_TEXTURE_SIZE={max_size}"
            )
        texture = self.ctx.texture(image.size, 4, image.tobytes(), alignment=1)
        texture.repeat_x = True
        texture.repeat_y = True
        texture.filter = (self.moderngl.LINEAR_MIPMAP_LINEAR, self.moderngl.LINEAR)
        texture.build_mipmaps()
        self._texture_cache[digest] = _GPUTexture(texture, digest)
        return texture

    @staticmethod
    def _matrix_bytes(matrix: tuple[float, ...]) -> bytes:
        return struct.pack("<16f", *matrix)

    def render(
        self,
        mesh: MeshData,
        *,
        cache_key: str,
        mode: str = "textured",
        width: int = 512,
        height: int = 512,
        camera: RenderCamera | None = None,
        model_yaw: float = 0.0,
        model_pitch: float = 0.0,
        background: tuple[float, float, float, float] = (0.055, 0.07, 0.085, 1.0),
    ) -> RenderFrame:
        mode_name = mode.casefold()
        if mode_name not in RENDER_MODES:
            raise ValueError(f"unknown OpenGL render mode: {mode}")
        width = max(32, min(int(width), MAX_FRAMEBUFFER_SIDE))
        height = max(32, min(int(height), MAX_FRAMEBUFFER_SIDE))
        gpu = self._gpu_mesh(mesh, cache_key)
        color = self.ctx.texture((width, height), 4, alignment=1)
        depth = self.ctx.depth_renderbuffer((width, height))
        fbo = self.ctx.framebuffer(color_attachments=[color], depth_attachment=depth)
        try:
            fbo.use()
            fbo.clear(*background, depth=1.0)
            self.ctx.enable(self.moderngl.DEPTH_TEST)
            self.ctx.enable(self.moderngl.BLEND)
            self.ctx.blend_func = (
                self.moderngl.SRC_ALPHA,
                self.moderngl.ONE_MINUS_SRC_ALPHA,
            )
            self.ctx.disable(self.moderngl.CULL_FACE)
            self.ctx.wireframe = mode_name == "wireframe"

            normalizer = normalization_matrix(gpu.compiled.minimum, gpu.compiled.maximum)
            rotation = mat_mul(rotation_x(model_pitch), rotation_z(model_yaw))
            model = mat_mul(rotation, normalizer)
            camera = camera or RenderCamera()
            view, projection = camera.matrices(width / height)
            self.program["u_model"].write(self._matrix_bytes(model))
            self.program["u_view"].write(self._matrix_bytes(view))
            self.program["u_projection"].write(self._matrix_bytes(projection))
            self.program["u_mode"].value = RENDER_MODES[mode_name]
            self.program["u_light_dir"].value = (0.35, -0.6, -0.72)
            self.program["u_texture"].value = 0

            for batch in gpu.batches:
                material = gpu.compiled.materials[batch.material_index]
                texture = self._texture(material.texture_path)
                texture.use(location=0)
                self.program["u_base_color"].value = material.base_color
                self.program["u_has_texture"].value = int(bool(material.texture_path))
                self.program["u_has_vertex_color"].value = 1
                batch.vertex_array.render(mode=self.moderngl.TRIANGLES)

            raw = fbo.read(components=4, alignment=1)
            try:
                from PIL import Image
            except ImportError as exc:  # pragma: no cover
                raise OpenGLUnavailable("Pillow is required for OpenGL framebuffer readback") from exc
            image = Image.frombytes("RGBA", (width, height), raw).transpose(Image.Transpose.FLIP_TOP_BOTTOM)
            rgba = image.tobytes()
            return RenderFrame(width, height, rgba, mode_name, camera.view, self.backend)
        finally:
            self.ctx.wireframe = False
            try:
                fbo.release()
            except Exception:
                pass
            try:
                depth.release()
            except Exception:
                pass
            try:
                color.release()
            except Exception:
                pass

    def render_three_views(
        self,
        mesh: MeshData,
        *,
        cache_key: str,
        mode: str = "textured",
        size: int = 512,
        model_yaw: float = 0.0,
        model_pitch: float = 0.0,
    ) -> dict[str, RenderFrame]:
        return {
            view: self.render(
                mesh,
                cache_key=cache_key,
                mode=mode,
                width=size,
                height=size,
                camera=RenderCamera(view=view, ortho_scale=1.15),
                model_yaw=model_yaw,
                model_pitch=model_pitch,
                background=(0.0, 0.0, 0.0, 1.0) if mode in {"silhouette", "depth"} else (0.055, 0.07, 0.085, 1.0),
            )
            for view in ("front", "top", "side")
        }
