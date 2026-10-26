import queue
import threading
import unittest
from unittest.mock import patch

from PIL import Image

import ndi_sender as ndi


class RenderTests(unittest.TestCase):
    def test_panel_has_full_hd_alpha_and_reserved_space(self):
        photo = Image.new("RGBA", (335, 245), "#59c3ec")
        with patch.object(ndi, "load_remote_image", return_value=photo):
            panel = ndi.draw_panel([{"title": "Titular de prueba", "section": "PAIS"}], 0)
        self.assertEqual(panel.size, (1920, 1080))
        self.assertEqual(panel.getpixel((100, 500))[3], 0)
        self.assertEqual(panel.getpixel((1600, 40))[3], 0)
        self.assertEqual(panel.getpixel((1600, 900))[3], 0)
        self.assertEqual(panel.getpixel((1600, 760))[:3], (0, 143, 88))

    def test_contain_preserves_complete_image_without_stretch(self):
        photo = Image.new("RGBA", (800, 400), "red")
        output = ndi.contain(photo, (300, 300))
        self.assertEqual(output.getbbox(), (0, 75, 300, 225))

    def test_transition_endpoints_keep_transparency(self):
        previous = Image.new("RGBA", (1920, 1080), (0, 0, 0, 0))
        current = previous.copy()
        previous.putpixel((1600, 500), (255, 0, 0, 255))
        current.putpixel((1600, 500), (0, 255, 0, 255))
        self.assertEqual(ndi.compose_transition(previous, current, 0).tobytes(), previous.tobytes())
        self.assertEqual(ndi.compose_transition(previous, current, 1).tobytes(), current.tobytes())

    def test_background_preparation_returns_complete_queue(self):
        updates = queue.Queue(maxsize=1)
        stop = threading.Event()

        def fetch():
            stop.set()
            return [{"url": "a"}, {"url": "b"}]

        with patch.object(ndi, "fetch_items", side_effect=fetch), \
                patch.object(ndi, "draw_panel", side_effect=lambda items, i: i):
            ndi.prepare_news(updates, stop)
        items, panels = updates.get_nowait()
        self.assertEqual(len(items), 2)
        self.assertEqual(panels, [0, 1])


if __name__ == "__main__":
    unittest.main()
