from __future__ import annotations

import argparse
import ctypes
import io
import json
import os
import logging
import platform
import signal
import time
import queue
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from urllib.request import Request, urlopen

import numpy as np
from PIL import Image, ImageDraw, ImageEnhance, ImageFilter, ImageFont

from config import API_URL, BASE_DIR, MAX_ITEMS, REFRESH_SECONDS, ROTATE_SECONDS, SOURCE_NAME, positive_int
from ndi_status import STATUS_FILE, write_status

WIDTH = 1920
HEIGHT = 1080
RAIL_X = 1556
RAIL_Y = 0
RAIL_W = 335
RAIL_H = 825
TOP_CLEAR = 78
FPS = positive_int("NDI_FPS", 30)
if FPS > 120:
    raise ValueError("NDI_FPS no puede superar 120")
NDI_DATA_DIR = Path(os.environ.get("NDI_DATA_DIR", str(BASE_DIR / "data" / "ndi")))
logger = logging.getLogger(__name__)
TRANSITION_SECONDS = 0.85
LOGO_PATH = BASE_DIR / "assets" / "el-deber-verde.png"
_dll_directory = None

SEA_GREEN = "#008F58"
SEA_GREEN_DARK = "#006B47"
PINK = "#E62F58"
PANEL = "#F3F6F4"
INK = "#10221A"
WHITE = "#FFFFFF"
MUTED = "#D2E9DF"


def font(path: str, size: int) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(path, size=size)


FONT_BODY = str(BASE_DIR / "assets" / "fonts" / "FlamaCondensed-Medium.ttf")
FONT_TITLE = str(BASE_DIR / "assets" / "fonts" / "FlamaCondensed-Black.ttf")
FONT_LABEL = str(BASE_DIR / "assets" / "fonts" / "FlamaCondensed-Bold.ttf")


class NDIlib_send_create_t(ctypes.Structure):
    _fields_ = [
        ("p_ndi_name", ctypes.c_char_p),
        ("p_groups", ctypes.c_char_p),
        ("clock_video", ctypes.c_bool),
        ("clock_audio", ctypes.c_bool),
    ]


class NDIlib_video_frame_v2_t(ctypes.Structure):
    _fields_ = [
        ("xres", ctypes.c_int),
        ("yres", ctypes.c_int),
        ("FourCC", ctypes.c_int),
        ("frame_rate_N", ctypes.c_int),
        ("frame_rate_D", ctypes.c_int),
        ("picture_aspect_ratio", ctypes.c_float),
        ("frame_format_type", ctypes.c_int),
        ("timecode", ctypes.c_int64),
        ("p_data", ctypes.POINTER(ctypes.c_ubyte)),
        ("line_stride_in_bytes", ctypes.c_int),
        ("p_metadata", ctypes.c_char_p),
        ("timestamp", ctypes.c_int64),
    ]


def fourcc(value: bytes) -> int:
    return int.from_bytes(value, "little")


def load_ndi():
    global _dll_directory
    if ctypes.sizeof(ctypes.c_void_p) != 8:
        raise RuntimeError("NDI requiere Python y runtime de 64 bits")
    configured = os.environ.get("NDI_LIBRARY_PATH")
    if platform.system() == "Windows":
        configured = configured or os.environ.get("NDI_DLL_PATH")
        program_files = Path(os.environ.get("ProgramFiles", r"C:\Program Files"))
        candidates = [Path(configured)] if configured else [
            program_files / "NDI" / f"NDI {version} Tools" / folder / filename
            for version in (6, 5)
            for folder, filename in (
                ("Runtime", "Processing.NDI.Lib.x64.dll"),
                ("Test Patterns", "Processing.NDI.Lib.Advanced.x64.dll"),
            )
        ]
        library = next((path for path in candidates if path.is_file()), None)
        if library is None:
            raise RuntimeError("Instala NDI Runtime o configura NDI_LIBRARY_PATH/NDI_DLL_PATH")
        _dll_directory = os.add_dll_directory(str(library.parent))
    elif platform.system() == "Linux":
        library = Path(configured or "/opt/ndi/libndi.so")
        if not library.is_file():
            raise RuntimeError(f"No existe el runtime oficial NDI Linux: {library}")
    else:
        raise RuntimeError("Plataforma soportada: Windows o Linux de 64 bits")
    # The SDK exports the C ABI (cdecl on Windows), with natural alignment.
    ndi = ctypes.CDLL(str(library))
    ndi.NDIlib_initialize.argtypes = []
    ndi.NDIlib_initialize.restype = ctypes.c_bool
    ndi.NDIlib_version.argtypes = []
    ndi.NDIlib_version.restype = ctypes.c_char_p
    ndi.NDIlib_send_create.argtypes = [ctypes.POINTER(NDIlib_send_create_t)]
    ndi.NDIlib_send_create.restype = ctypes.c_void_p
    ndi.NDIlib_send_send_video_v2.argtypes = [
        ctypes.c_void_p,
        ctypes.POINTER(NDIlib_video_frame_v2_t),
    ]
    ndi.NDIlib_send_send_video_v2.restype = None
    ndi.NDIlib_send_destroy.argtypes = [ctypes.c_void_p]
    ndi.NDIlib_send_destroy.restype = None
    ndi.NDIlib_destroy.argtypes = []
    ndi.NDIlib_destroy.restype = None
    ndi.NDIlib_send_get_no_connections.argtypes = [ctypes.c_void_p, ctypes.c_uint32]
    ndi.NDIlib_send_get_no_connections.restype = ctypes.c_int
    logger.info("Runtime NDI: %s (%s)", ndi.NDIlib_version(), library)
    return ndi


def fetch_json(url: str) -> dict:
    request = Request(url, headers={"User-Agent": "ED24-NDI/1.0"})
    with urlopen(request, timeout=12) as response:
        return json.loads(response.read().decode("utf-8"))


def fetch_items() -> list[dict]:
    try:
        payload = fetch_json(API_URL)
        items = payload.get("items", [])
        if items:
            return validate_items(items)
        logger.warning("API sin titulares; se conserva la cola anterior")
    except Exception as error:
        logger.warning("API no disponible; se conserva la cola anterior: %s", error)
    return []


def validate_items(items) -> list[dict]:
    if not isinstance(items, list):
        raise ValueError("items debe ser una lista")
    return [item for item in items if isinstance(item, dict)
            and isinstance(item.get("title"), str) and item["title"].strip()
            and all(isinstance(item.get(key, ""), str)
                    for key in ("url", "image", "section"))][:MAX_ITEMS]


def saved_items() -> list[dict]:
    try:
        return validate_items(json.loads((NDI_DATA_DIR / "headlines.json").read_text("utf-8")))
    except (OSError, ValueError):
        return []


def persist_items(items):
    NDI_DATA_DIR.mkdir(parents=True, exist_ok=True)
    temporary = NDI_DATA_DIR / "headlines.tmp"
    temporary.write_text(json.dumps(items, ensure_ascii=False), encoding="utf-8")
    temporary.replace(NDI_DATA_DIR / "headlines.json")


def load_remote_image(url: str, size: tuple[int, int]) -> Image.Image:
    try:
        request = Request(
            url,
            headers={
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/124.0 Safari/537.36"
                )
            },
        )
        with urlopen(request, timeout=12) as response:
            raw = response.read()
        image = Image.open(io.BytesIO(raw)).convert("RGBA")
    except Exception:
        return Image.new("RGBA", size, PANEL)

    background = cover(image, size).filter(ImageFilter.GaussianBlur(13))
    background = ImageEnhance.Brightness(background).enhance(0.72)
    foreground = contain(image, size)
    background.alpha_composite(foreground)
    return background


def cover(image: Image.Image, size: tuple[int, int]) -> Image.Image:
    target_w, target_h = size
    scale = max(target_w / image.width, target_h / image.height)
    new_size = (max(1, int(image.width * scale)), max(1, int(image.height * scale)))
    resized = image.resize(new_size, Image.LANCZOS)
    left = (resized.width - target_w) // 2
    top = (resized.height - target_h) // 2
    return resized.crop((left, top, left + target_w, top + target_h))


def contain(image: Image.Image, size: tuple[int, int]) -> Image.Image:
    target_w, target_h = size
    scale = min(target_w / image.width, target_h / image.height)
    new_size = (max(1, int(image.width * scale)), max(1, int(image.height * scale)))
    resized = image.resize(new_size, Image.LANCZOS)
    result = Image.new("RGBA", size, (0, 0, 0, 0))
    left = (target_w - resized.width) // 2
    top = (target_h - resized.height) // 2
    result.alpha_composite(resized, (left, top))
    return result


def text_size(draw: ImageDraw.ImageDraw, text: str, font_obj: ImageFont.FreeTypeFont):
    bbox = draw.textbbox((0, 0), text, font=font_obj)
    return bbox[2] - bbox[0], bbox[3] - bbox[1]


def wrap_text(draw: ImageDraw.ImageDraw, text: str, font_obj, max_width: int) -> list[str]:
    words = text.upper().split()
    lines: list[str] = []
    line = ""
    for word in words:
        candidate = f"{line} {word}".strip()
        if text_size(draw, candidate, font_obj)[0] <= max_width:
            line = candidate
        else:
            if line:
                lines.append(line)
            line = word
    if line:
        lines.append(line)
    return lines


def fit_multiline(
    draw: ImageDraw.ImageDraw,
    text: str,
    font_path: str,
    max_width: int,
    max_height: int,
    start_size: int,
    min_size: int,
) -> tuple[ImageFont.FreeTypeFont, list[str], int]:
    for size in range(start_size, min_size - 1, -1):
        font_obj = font(font_path, size)
        lines = wrap_text(draw, text, font_obj, max_width)
        line_gap = max(2, int(size * 0.08))
        height = len(lines) * size + max(0, len(lines) - 1) * line_gap
        if height <= max_height:
            return font_obj, lines, line_gap
    font_obj = font(font_path, min_size)
    lines = wrap_text(draw, text, font_obj, max_width)
    return font_obj, lines[: max(1, max_height // min_size)], 2


def draw_multiline(
    draw: ImageDraw.ImageDraw,
    xy: tuple[int, int],
    lines: list[str],
    font_obj,
    fill: str,
    line_gap: int,
):
    x, y = xy
    for line in lines:
        draw.text((x, y), line, font=font_obj, fill=fill)
        y += font_obj.size + line_gap


def draw_shadow(base: Image.Image):
    shadow = Image.new("RGBA", (34, RAIL_H), (0, 0, 0, 0))
    d = ImageDraw.Draw(shadow)
    for x in range(34):
        alpha = int(90 * (1 - x / 34) ** 1.8)
        d.line((33 - x, 0, 33 - x, RAIL_H), fill=(0, 0, 0, alpha))
    base.alpha_composite(shadow, (RAIL_X - 34, RAIL_Y))


def draw_panel(items: list[dict], index: int) -> Image.Image:
    canvas = Image.new("RGBA", (WIDTH, HEIGHT), (0, 0, 0, 0))
    panel = Image.new("RGBA", (RAIL_W, RAIL_H), (0, 0, 0, 0))
    draw = ImageDraw.Draw(panel)

    draw.rectangle((0, TOP_CLEAR, RAIL_W, RAIL_H), fill=PANEL)
    draw.rectangle((0, TOP_CLEAR, 4, RAIL_H), fill=SEA_GREEN)
    draw.rectangle((RAIL_W - 5, TOP_CLEAR, RAIL_W, RAIL_H), fill=SEA_GREEN)
    draw.rectangle((0, TOP_CLEAR, RAIL_W, TOP_CLEAR + 4), fill=SEA_GREEN)
    draw.rectangle((0, RAIL_H - 5, RAIL_W, RAIL_H), fill=SEA_GREEN)

    if not items:
        items = [{
            "title": "SIN TITULARES DISPONIBLES",
            "section": "PORTADA",
            "image": "",
        }]

    current = items[index % len(items)]
    image = load_remote_image(current.get("image", ""), (RAIL_W, 245))
    panel.alpha_composite(image, (0, TOP_CLEAR + 4))
    draw.rectangle((0, 332, RAIL_W, RAIL_H - 5), fill=PANEL)
    draw.rectangle((0, 327, RAIL_W, 332), fill=SEA_GREEN)

    draw.rectangle((20, 357, 27, 724), fill=SEA_GREEN)
    title_font, title_lines, title_gap = fit_multiline(
        draw,
        current.get("title", ""),
        FONT_TITLE,
        274,
        340,
        49,
        30,
    )
    draw_multiline(draw, (42, 357), title_lines, title_font, INK, title_gap)

    section = (current.get("section") or "PORTADA").upper()[:24]
    section_font = font(FONT_LABEL, 25)
    section_w = min(270, max(174, text_size(draw, section, section_font)[0] + 44))
    button_y = 746
    draw.rounded_rectangle(
        (42, button_y, 42 + section_w, button_y + 52),
        radius=4,
        fill=SEA_GREEN,
    )
    draw.rectangle(
        (42, button_y + 48, 42 + section_w, button_y + 52),
        fill=SEA_GREEN_DARK,
    )
    draw.text((64, button_y + 11), section, font=section_font, fill=WHITE)

    canvas.alpha_composite(panel, (RAIL_X, RAIL_Y))
    return canvas


def to_bgra_buffer(image: Image.Image):
    arr = np.asarray(image.convert("RGBA"), dtype=np.uint8)
    bgra = arr[:, :, [2, 1, 0, 3]].copy()
    return ctypes.create_string_buffer(bgra.tobytes(), bgra.nbytes)


def make_video_frame(buffer):
    return NDIlib_video_frame_v2_t(
        xres=WIDTH, yres=HEIGHT, FourCC=fourcc(b"BGRA"),
        frame_rate_N=FPS, frame_rate_D=1, picture_aspect_ratio=WIDTH / HEIGHT,
        frame_format_type=1,  # NDIlib_frame_format_type_progressive
        timecode=0x7FFFFFFFFFFFFFFF,  # NDIlib_send_timecode_synthesize
        p_data=ctypes.cast(buffer, ctypes.POINTER(ctypes.c_ubyte)),
        line_stride_in_bytes=WIDTH * 4, p_metadata=None, timestamp=0,
    )


def ease_transition(value: float) -> float:
    value = max(0.0, min(1.0, value))
    return value * value * (3 - 2 * value)


def composite_shifted(base: Image.Image, layer: Image.Image, dx: int, alpha: float):
    layer = layer.convert("RGBA")
    if alpha < 1:
        layer = layer.copy()
        alpha_channel = layer.getchannel("A").point(lambda px: int(px * alpha))
        layer.putalpha(alpha_channel)

    if dx < 0:
        crop = layer.crop((-dx, 0, WIDTH, HEIGHT))
        base.alpha_composite(crop, (0, 0))
    elif dx > 0:
        crop = layer.crop((0, 0, WIDTH - dx, HEIGHT))
        base.alpha_composite(crop, (dx, 0))
    else:
        base.alpha_composite(layer, (0, 0))


def compose_transition(previous: Image.Image, current: Image.Image, progress: float):
    eased = ease_transition(progress)
    frame = Image.new("RGBA", (WIDTH, HEIGHT), (0, 0, 0, 0))
    composite_shifted(frame, previous, int(-18 * eased), 1 - eased)
    composite_shifted(frame, current, int(28 * (1 - eased)), eased)
    return frame


def prepare_news(updates: queue.Queue, stop: threading.Event):
    # Download and render off the video thread so NDI keeps emitting frames.
    def publish(items):
        with ThreadPoolExecutor(max_workers=4) as executor:
            panels = list(executor.map(lambda i: draw_panel(items, i), range(len(items))))
        try:
            updates.get_nowait()
        except queue.Empty:
            pass
        updates.put_nowait((items, panels))

    previous = saved_items()
    if previous:
        try:
            publish(previous)
        except Exception:
            logger.exception("No se pudo renderizar la cola persistida")
            previous = []
    while not stop.is_set():
        items = []
        try:
            items = fetch_items()
            if items:
                # Avoid replacing valid photos with placeholders on API failure.
                if items != previous:
                    publish(items)
                    previous = items
                persist_items(items)
        except Exception as error:
            logger.exception("No se pudo actualizar NDI: %s", error)
        stop.wait(REFRESH_SECONDS if items else 15)


def run_sender(name: str, stop: threading.Event | None = None):
    stop = stop if stop is not None else threading.Event()
    ndi = load_ndi()
    if not ndi.NDIlib_initialize():
        raise RuntimeError("No se pudo inicializar NDI")

    settings = NDIlib_send_create_t(
        p_ndi_name=name.encode("utf-8"),
        p_groups=None,
        clock_video=True,
        clock_audio=False,
    )
    sender = ndi.NDIlib_send_create(ctypes.byref(settings))
    if not sender:
        ndi.NDIlib_destroy()
        raise RuntimeError("No se pudo crear la salida NDI")

    print(f"NDI activo: {name}")
    print(f"Formato: 1920x1080 BGRA con alpha, {FPS} FPS; API: {API_URL}")
    print("NDI® is a registered trademark of Vizrt NDI AB — https://ndi.video/")
    print("Ctrl+C para detener")

    updates = queue.Queue(maxsize=1)
    threading.Thread(target=prepare_news, args=(updates, stop), daemon=True).start()
    items: list[dict] = []
    panels = [draw_panel([], 0)]
    current_index = 0
    previous_image = panels[0]
    transition_start = time.monotonic() - TRANSITION_SECONDS
    next_rotation = time.monotonic() + ROTATE_SECONDS
    buffer = to_bgra_buffer(panels[0])
    static_frame = True
    pending = None
    frame_interval = 1 / FPS
    frames = 0
    last_status = last_log = time.monotonic()

    try:
        while not stop.is_set():
            now = time.monotonic()
            try:
                pending = updates.get_nowait()
            except queue.Empty:
                pass

            if (pending and not items) or now >= next_rotation:
                previous_image = panels[current_index]
                next_index = (current_index + 1) % len(panels)
                next_url = items[next_index].get("url") if items else None
                if pending:
                    items, panels = pending
                    pending = None
                    next_index = next((i for i, item in enumerate(items)
                                       if next_url and item.get("url") == next_url), 0)
                current_index = next_index
                transition_start = now
                next_rotation = now + ROTATE_SECONDS
                static_frame = False

            progress = (now - transition_start) / TRANSITION_SECONDS
            if progress < 1:
                image = compose_transition(
                    previous_image,
                    panels[current_index],
                    progress,
                )
                buffer = to_bgra_buffer(image)
            elif not static_frame:
                image = panels[current_index]
                buffer = to_bgra_buffer(image)
                static_frame = True

            frame = make_video_frame(buffer)
            ndi.NDIlib_send_send_video_v2(sender, ctypes.byref(frame))
            frames += 1
            sent_at = time.monotonic()
            if sent_at - last_status >= 1:
                # Only a returned send call advances the heartbeat.
                write_status(STATUS_FILE, frames=frames, items=len(items), name=name,
                             fps=FPS, connections=ndi.NDIlib_send_get_no_connections(sender, 0))
                last_status = sent_at
            if sent_at - last_log >= 30:
                logger.info("NDI frames=%s items=%s FPS objetivo=%s", frames, len(items), FPS)
                last_log = sent_at
            # clock_video already throttles SDK submission; never add another full interval.
            stop.wait(max(0, frame_interval - (time.monotonic() - now)))
    finally:
        stop.set()
        ndi.NDIlib_send_destroy(sender)
        ndi.NDIlib_destroy()


def save_preview(path: Path):
    items = fetch_items()
    image = draw_panel(items, 0)
    image.save(path)
    print(path)


def main():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    parser = argparse.ArgumentParser()
    parser.add_argument("--name", default=SOURCE_NAME)
    parser.add_argument("--preview", action="store_true")
    parser.add_argument("--check-runtime", action="store_true",
                        help="Carga e inicializa el SDK sin crear una fuente ni emitir")
    args = parser.parse_args()

    if args.check_runtime:
        ndi = load_ndi()
        if not ndi.NDIlib_initialize():
            raise RuntimeError("El runtime no se pudo inicializar en esta CPU/plataforma")
        ndi.NDIlib_destroy()
        print("OK: runtime cargado e inicializado; no se ha emitido video")
        return

    if args.preview:
        save_preview(BASE_DIR / "preview_ndi.png")
        return

    stop = threading.Event()
    for sig in (signal.SIGINT, signal.SIGTERM):
        signal.signal(sig, lambda *_: stop.set())
    run_sender(args.name, stop)


if __name__ == "__main__":
    main()
