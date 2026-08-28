from __future__ import annotations

import importlib.util
import unittest

from ourd_gui.mesh_formats import MeshData, MeshFace
from ourd_gui.opengl.math3d import RenderCamera
from ourd_gui.opengl.renderer import OpenGLUnavailable
from ourd_gui.opengl.service import OpenGLRenderService


HAS_MODERNGL = importlib.util.find_spec("moderngl") is not None
HAS_PILLOW = importlib.util.find_spec("PIL") is not None


@unittest.skipUnless(HAS_MODERNGL and HAS_PILLOW, "optional OpenGL/Pillow dependencies are not installed")
class OpenGLRendererOptionalTests(unittest.TestCase):
    def test_headless_context_renders_triangle_when_platform_supports_it(self) -> None:
        mesh = MeshData(
            name="triangle",
            vertices=((-0.8, 0.0, -0.6), (0.8, 0.0, -0.6), (0.0, 0.0, 0.8)),
            edges=(),
            faces=(MeshFace((0, 1, 2)),),
        )
        service = OpenGLRenderService(timeout_seconds=20.0)
        try:
            try:
                capabilities = service.capabilities()
            except OpenGLUnavailable as exc:
                self.skipTest(f"platform has no usable headless OpenGL context: {exc}")
            self.assertGreaterEqual(capabilities.version_code, 330)
            frame = service.render(
                mesh,
                cache_key="test:triangle",
                mode="silhouette",
                width=96,
                height=96,
                camera=RenderCamera(view="front"),
            )
            self.assertEqual((96, 96), (frame.width, frame.height))
            self.assertEqual(96 * 96 * 4, len(frame.rgba))
            self.assertTrue(frame.to_png_bytes().startswith(b"\x89PNG"))
        finally:
            service.close()


if __name__ == "__main__":
    unittest.main()
