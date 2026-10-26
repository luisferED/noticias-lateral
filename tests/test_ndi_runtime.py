import ctypes
import json
import queue
import tempfile
import threading
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch
from urllib.error import URLError

from PIL import Image
from waitress import create_server

import ndi_sender as ndi
import ndi_service
import ndi_status
import server


ITEM = {"title": "Titular de prueba con imagen para la integración de API y NDI",
        "url": "https://eldeber.com.bo/pais/prueba", "image": "https://eldeber.com.bo/a.jpg",
        "section": "PAIS"}


class RuntimeTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.directory = Path(directory.name)
        for name, value in (("NDI_DATA_DIR", self.directory),
                            ("STATUS_FILE", self.directory / "status.json")):
            patcher = patch.object(ndi, name, value)
            patcher.start()
            self.addCleanup(patcher.stop)

    def test_bgra_exact_size_straight_alpha_and_frame_metadata(self):
        image = Image.new("RGBA", (1920, 1080), (0, 0, 0, 0))
        image.putpixel((1, 0), (123, 45, 67, 128))
        buffer = ndi.to_bgra_buffer(image)
        self.assertEqual(ctypes.sizeof(buffer), 1920 * 1080 * 4)
        self.assertEqual(buffer.raw[:8], bytes([0, 0, 0, 0, 67, 45, 123, 128]))
        frame = ndi.make_video_frame(buffer)
        self.assertEqual((frame.xres, frame.yres, frame.frame_rate_N, frame.frame_rate_D),
                         (1920, 1080, ndi.FPS, 1))
        self.assertEqual(frame.FourCC, ndi.fourcc(b"BGRA"))
        self.assertEqual(frame.line_stride_in_bytes, 7680)
        self.assertEqual(frame.frame_format_type, 1)
        self.assertEqual(frame.timecode, (1 << 63) - 1)
        self.assertEqual(ctypes.string_at(frame.p_data, 8), buffer.raw[:8])

    def test_x64_layout_matches_current_sdk_abi_expectations(self):
        self.assertEqual(ctypes.sizeof(ctypes.c_void_p), 8)
        self.assertEqual(ctypes.sizeof(ndi.NDIlib_send_create_t), 24)
        self.assertEqual(ctypes.sizeof(ndi.NDIlib_video_frame_v2_t), 72)
        for name, offset in {"timecode": 32, "p_data": 40, "line_stride_in_bytes": 48,
                             "p_metadata": 56, "timestamp": 64}.items():
            self.assertEqual(getattr(ndi.NDIlib_video_frame_v2_t, name).offset, offset)

    def test_linux_loader_uses_cdll_and_declares_signatures(self):
        library = self.directory / "libndi.so"
        library.touch()
        runtime = Mock()
        with patch.object(ndi.platform, "system", return_value="Linux"), \
                patch.dict(ndi.os.environ, {"NDI_LIBRARY_PATH": str(library)}), \
                patch.object(ndi.ctypes, "CDLL", return_value=runtime) as load:
            self.assertIs(ndi.load_ndi(), runtime)
        load.assert_called_once_with(str(library))
        self.assertIs(runtime.NDIlib_initialize.restype, ctypes.c_bool)
        self.assertIs(runtime.NDIlib_send_create.restype, ctypes.c_void_p)
        self.assertEqual(runtime.NDIlib_send_send_video_v2.argtypes,
                         [ctypes.c_void_p, ctypes.POINTER(ndi.NDIlib_video_frame_v2_t)])

    def test_windows_loader_keeps_legacy_dll_variable(self):
        library = self.directory / "Processing.NDI.Lib.x64.dll"
        library.touch()
        with patch.object(ndi.platform, "system", return_value="Windows"), \
                patch.dict(ndi.os.environ, {"NDI_LIBRARY_PATH": "", "NDI_DLL_PATH": str(library)}), \
                patch.object(ndi.os, "add_dll_directory", return_value=Mock(), create=True) as add, \
                patch.object(ndi.ctypes, "CDLL", return_value=Mock()) as load:
            ndi.load_ndi()
        add.assert_called_once_with(str(library.parent))
        load.assert_called_once_with(str(library))

    def test_missing_linux_runtime_has_actionable_error(self):
        with patch.object(ndi.platform, "system", return_value="Linux"), \
                patch.dict(ndi.os.environ, {"NDI_LIBRARY_PATH": str(self.directory / "missing.so")}):
            with self.assertRaisesRegex(RuntimeError, "runtime oficial"):
                ndi.load_ndi()

    def test_api_failure_does_not_publish_empty_queue_or_replace_saved_items(self):
        ndi.persist_items([ITEM])
        stop = threading.Event()
        updates = queue.Queue()

        def offline(url):
            stop.set()
            raise URLError("offline")

        with patch.object(ndi, "fetch_json", side_effect=offline), \
                patch.object(ndi, "draw_panel", return_value="saved-panel"):
            ndi.prepare_news(updates, stop)
        items, panels = updates.get_nowait()
        self.assertEqual(items, [ITEM])
        self.assertEqual(panels, ["saved-panel"])
        self.assertEqual(ndi.saved_items(), [ITEM])
        self.assertTrue(updates.empty())

    def test_health_requires_completed_frames_and_fresh_heartbeat(self):
        self.assertFalse(ndi_status.is_healthy({}))
        self.assertFalse(ndi_status.is_healthy({"frames": 0, "monotonic": 100}, 101))
        status = {"frames": 30, "monotonic": 100, "pid": 123}
        self.assertTrue(ndi_status.is_healthy(status, 101, 123))
        self.assertFalse(ndi_status.is_healthy(status, 101, 124))
        self.assertFalse(ndi_status.is_healthy(status, 100 + ndi_status.STALL_SECONDS))

    def test_supervisor_exits_on_blocked_sender_and_ignores_old_process_heartbeat(self):
        child = SimpleNamespace(pid=123, poll=lambda: None)
        stop = Mock()
        stop.wait.return_value = False
        stale = {"frames": 30, "monotonic": 10, "pid": 123}
        with patch.object(ndi_service, "read_status", return_value=stale), \
                patch.object(ndi_service.time, "monotonic", return_value=1000):
            self.assertEqual(ndi_service.monitor(child, stop, 1), 1)
        previous = {"frames": 30, "monotonic": 1000, "pid": 999}
        with patch.object(ndi_service, "read_status", return_value=previous), \
                patch.object(ndi_service.time, "monotonic", return_value=1000):
            self.assertEqual(ndi_service.monitor(child, stop, 1), 1)

    def test_supervisor_exits_if_child_crashes(self):
        child = SimpleNamespace(pid=123, poll=lambda: 17)
        stop = Mock()
        stop.wait.return_value = False
        self.assertEqual(ndi_service.monitor(child, stop, 1), 17)

    def test_http_api_to_sender_with_fake_sdk_and_clean_shutdown(self):
        # Actual HTTP/Waitress + rendered panel + native ABI frame; only SDK is fake.
        payload = {"ok": True, "updated_at": int(time.time()), "items": [ITEM]}
        stop = threading.Event()
        runtime = Mock()
        runtime.NDIlib_initialize.return_value = True
        runtime.NDIlib_send_create.return_value = 1
        runtime.NDIlib_send_get_no_connections.return_value = 1
        frames = []

        def send(sender, pointer):
            frame = ctypes.cast(pointer, ctypes.POINTER(ndi.NDIlib_video_frame_v2_t)).contents
            frames.append((frame.xres, frame.yres, frame.frame_rate_N, frame.p_data[3]))
            if len(frames) >= 45:
                stop.set()

        runtime.NDIlib_send_send_video_v2.side_effect = send
        with patch.object(server, "_cache", {"payload": payload, "expires_at": time.time()+180}):
            http = create_server(server.app, host="127.0.0.1", port=0, threads=2)
            thread = threading.Thread(target=http.run, daemon=True)
            thread.start()
            try:
                with patch.object(ndi, "API_URL", f"http://127.0.0.1:{http.effective_port}/api/headlines"), \
                        patch.object(ndi, "load_ndi", return_value=runtime), \
                        patch.object(ndi, "load_remote_image", return_value=Image.new("RGBA", (335,245), "red")):
                    ndi.run_sender("TEST_NO_NETWORK_NDI", stop)
                self.assertEqual(ndi.saved_items(), [ITEM])
                status = json.loads((self.directory / "status.json").read_text())
                self.assertGreater(status["frames"], 0)
                self.assertEqual(status["items"], 1)
                self.assertEqual(len(frames), 45)
                self.assertTrue(all(frame == (1920,1080,ndi.FPS,0) for frame in frames))
                runtime.NDIlib_send_destroy.assert_called_once_with(1)
                runtime.NDIlib_destroy.assert_called_once()
            finally:
                stop.set()
                http.close()
                http.task_dispatcher.shutdown()


if __name__ == "__main__":
    unittest.main()
