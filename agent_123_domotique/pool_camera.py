"""Lecture locale des afficheurs AstralPool Micro pH et Micro Rx.

Le lecteur est volontairement spécialisé pour des afficheurs sept segments rouges.
Il ne commande aucun équipement et ne contacte aucun service distant.
"""

from __future__ import annotations

import io
import json
import time
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from PIL import Image


SEGMENTS = {
    frozenset("abcdef"): "0",
    frozenset("bc"): "1",
    frozenset("abdeg"): "2",
    frozenset("abcdg"): "3",
    frozenset("bcfg"): "4",
    frozenset("acdfg"): "5",
    frozenset("acdefg"): "6",
    frozenset("abc"): "7",
    frozenset("abcdefg"): "8",
    frozenset("abcdfg"): "9",
    frozenset("abcefg"): "A",
    frozenset("def"): "L",
}

DEFAULT_REGIONS = {
    # Coordonnées normalisées après correction miroir, pour le cadrage validé.
    "ph": (0.34, 0.45, 0.54, 0.66),
    "orp": (0.50, 0.43, 0.76, 0.64),
}


@dataclass(frozen=True)
class PoolReading:
    ph: float | None
    orp_mv: int | None
    alarm: bool
    ph_text: str | None
    orp_text: str | None
    confidence: float


def _red_mask(image: Image.Image, threshold: int = 145) -> list[list[bool]]:
    rgb = image.convert("RGB")
    width, height = rgb.size
    pixels = rgb.load()
    mask: list[list[bool]] = []
    for y in range(height):
        row = []
        for x in range(width):
            red, green, blue = pixels[x, y]
            row.append(red >= threshold and red >= green * 1.45 and red >= blue * 1.25)
        mask.append(row)
    return mask


def _runs(values: list[int], minimum: int = 1) -> list[tuple[int, int]]:
    result: list[tuple[int, int]] = []
    start = None
    for index, value in enumerate(values + [0]):
        if value >= minimum and start is None:
            start = index
        elif value < minimum and start is not None:
            if index - start >= 2:
                result.append((start, index))
            start = None
    return result


def _sample(mask: list[list[bool]], x0: float, y0: float, x1: float, y1: float) -> float:
    height = len(mask)
    width = len(mask[0]) if height else 0
    left, right = max(0, int(x0 * width)), min(width, max(1, int(x1 * width)))
    top, bottom = max(0, int(y0 * height)), min(height, max(1, int(y1 * height)))
    total = max(1, (right - left) * (bottom - top))
    lit = sum(mask[y][x] for y in range(top, bottom) for x in range(left, right))
    return lit / total


def _classify_character(image: Image.Image) -> tuple[str | None, float]:
    geometry = _red_mask(image, threshold=95)
    lit_x = [x for y, row in enumerate(geometry) for x, value in enumerate(row) if value]
    lit_y = [y for y, row in enumerate(geometry) for x, value in enumerate(row) if value]
    if not lit_x or not lit_y:
        return None, 0.0
    image = image.crop((
        max(0, min(lit_x) - 1), max(0, min(lit_y) - 1),
        min(image.width, max(lit_x) + 2), min(image.height, max(lit_y) + 2),
    ))
    mask = _red_mask(image.resize((40, 72)))
    patches = {
        "a": (0.20, 0.02, 0.80, 0.19),
        "b": (0.70, 0.12, 0.98, 0.49),
        "c": (0.70, 0.51, 0.98, 0.90),
        "d": (0.20, 0.82, 0.80, 1.00),
        "e": (0.02, 0.51, 0.30, 0.90),
        "f": (0.02, 0.12, 0.30, 0.49),
        "g": (0.20, 0.41, 0.80, 0.61),
    }
    scores = {name: _sample(mask, *box) for name, box in patches.items()}
    active = frozenset(name for name, score in scores.items() if score >= 0.16)
    exact = SEGMENTS.get(active)
    if exact:
        margin = min(
            [scores[name] - 0.16 for name in active]
            + [0.16 - scores[name] for name in patches if name not in active]
        )
        return exact, max(0.55, min(0.99, 0.7 + margin))
    best_char = None
    best_distance = 8
    for segments, character in SEGMENTS.items():
        distance = len(active.symmetric_difference(segments))
        if distance < best_distance:
            best_char, best_distance = character, distance
    return (best_char, 0.45) if best_distance <= 1 else (None, 0.0)


def _decode_two_characters(image: Image.Image) -> tuple[str | None, float]:
    # Le halo faible sert à localiser le groupe, puis la classification utilise
    # un seuil élevé afin de ne conserver que le cœur des segments.
    mask = _red_mask(image, threshold=75)
    height = len(mask)
    width = len(mask[0]) if height else 0
    columns = [sum(mask[y][x] for y in range(height)) for x in range(width)]
    candidates = _runs(columns, minimum=1)
    if not candidates:
        return None, 0.0
    # Le halo rouge relie souvent les deux caractères en une seule projection.
    # Le groupe de caractères est plus large et plus lumineux que le voyant ALARM.
    start, end = max(candidates, key=lambda run: sum(columns[run[0]:run[1]]))
    if end - start < 8:
        return None, 0.0
    lit_rows = [y for y in range(height) if any(mask[y][x] for x in range(start, end))]
    if not lit_rows:
        return None, 0.0
    top, bottom = max(0, min(lit_rows) - 2), min(height, max(lit_rows) + 3)
    center = (start + end) / 2
    character_ranges = [(start, int(center)), (int(center), end)]
    characters = []
    confidences = []
    for left, right in character_ranges:
        left, right = max(0, left - 1), min(width, right + 1)
        character, confidence = _classify_character(image.crop((left, top, right, bottom)))
        if not character:
            return None, 0.0
        characters.append(character)
        confidences.append(confidence)
    return "".join(characters), min(confidences)


def _crop(image: Image.Image, region: tuple[float, float, float, float]) -> Image.Image:
    width, height = image.size
    return image.crop((
        int(region[0] * width), int(region[1] * height),
        int(region[2] * width), int(region[3] * height),
    ))


def read_pool_image(
    image: Image.Image,
    *,
    mirror: bool = True,
    regions: dict[str, tuple[float, float, float, float]] | None = None,
) -> PoolReading:
    if mirror:
        image = image.transpose(Image.Transpose.FLIP_LEFT_RIGHT)
    regions = regions or DEFAULT_REGIONS
    ph_text, ph_confidence = _decode_two_characters(_crop(image, regions["ph"]))
    orp_text, orp_confidence = _decode_two_characters(_crop(image, regions["orp"]))
    # À cette distance, le halo peut fermer les deux ouvertures du A et le faire
    # ressembler à 0 ou 8. Un second caractère L rend néanmoins l'état non ambigu.
    if ph_text in {"0L", "8L"}:
        ph_text = "AL"
    ph = None
    if ph_text and ph_text.isdigit():
        value = int(ph_text) / 10
        ph = value if 4.0 <= value <= 10.0 else None
    orp_mv = None
    if orp_text and orp_text.isdigit():
        value = int(orp_text) * 10  # Le zéro des Micro Rx est sérigraphié.
        orp_mv = value if 0 <= value <= 990 else None
    alarm = ph_text == "AL"
    valid_confidences = [value for value in (ph_confidence, orp_confidence) if value > 0]
    confidence = min(valid_confidences) if valid_confidences else 0.0
    return PoolReading(ph, orp_mv, alarm, ph_text, orp_text, confidence)


def fetch_pool_image(url: str, timeout: int = 8) -> Image.Image:
    request = urllib.request.Request(url, headers={"User-Agent": "Agent-123-Domotique/PoolCamera"})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return Image.open(io.BytesIO(response.read())).convert("RGB")


def load_camera_state(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        return value if isinstance(value, dict) else {}
    except (FileNotFoundError, OSError, json.JSONDecodeError):
        return {}


def confirmed_reading(history: list[dict[str, Any]], minimum: int = 2) -> PoolReading | None:
    recent = history[-3:]
    if len(recent) < minimum:
        return None
    keys = [(row.get("ph"), row.get("orp_mv"), row.get("alarm")) for row in recent]
    winner = max(set(keys), key=keys.count)
    if keys.count(winner) < minimum:
        return None
    matching = [row for row in recent if (row.get("ph"), row.get("orp_mv"), row.get("alarm")) == winner]
    latest = matching[-1]
    return PoolReading(
        ph=latest.get("ph"),
        orp_mv=latest.get("orp_mv"),
        alarm=bool(latest.get("alarm")),
        ph_text=latest.get("ph_text"),
        orp_text=latest.get("orp_text"),
        confidence=float(latest.get("confidence", 0)),
    )


def reading_record(reading: PoolReading) -> dict[str, Any]:
    return {
        "at": int(time.time()),
        "ph": reading.ph,
        "orp_mv": reading.orp_mv,
        "alarm": reading.alarm,
        "ph_text": reading.ph_text,
        "orp_text": reading.orp_text,
        "confidence": reading.confidence,
    }
