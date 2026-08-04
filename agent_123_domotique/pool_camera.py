"""Lecture locale des afficheurs AstralPool Micro pH et Micro Rx.

Le lecteur est volontairement spécialisé pour des afficheurs sept segments rouges.
Il ne commande aucun équipement et ne contacte aucun service distant.
"""

from __future__ import annotations

import io
import json
import time
import urllib.request
from collections import Counter
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
    "ph": (0.20, 0.40, 0.42, 0.58),
    "orp": (0.52, 0.40, 0.72, 0.58),
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
            strongly_red = red >= green * 1.45 and red >= blue * 1.25
            saturated_orange = red >= 220 and red - green >= 20 and red - blue >= 40
            row.append(red >= threshold and (strongly_red or saturated_orange))
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
    active = frozenset(name for name, score in scores.items() if score >= 0.20)
    exact = SEGMENTS.get(active)
    if exact:
        margin = min(
            [scores[name] - 0.20 for name in active]
            + [0.20 - scores[name] for name in patches if name not in active]
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

    groups = []
    for start, end in candidates:
        lit_rows = [y for y in range(height) if any(mask[y][x] for x in range(start, end))]
        if lit_rows:
            groups.append((start, end, min(lit_rows), max(lit_rows) + 1, sum(columns[start:end])))
    if not groups:
        return None, 0.0

    # Écarte les voyants ALARM et les points décimaux, nettement moins hauts que
    # les chiffres. Le chiffre 1 reste volontairement accepté malgré sa faible largeur.
    tallest = max(bottom - top for _, _, top, bottom, _ in groups)
    digit_groups = [group for group in groups if group[3] - group[2] >= max(8, tallest * 0.65)]

    def classify_range(
        left: int,
        right: int,
        top: int,
        bottom: int,
        *,
        allow_skinny_one: bool = True,
    ) -> tuple[str | None, float]:
        if allow_skinny_one and (right - left) / max(1, bottom - top) <= 0.75:
            return "1", 0.8
        return _classify_character(image.crop((max(0, left - 1), max(0, top - 2), min(width, right + 1), min(height, bottom + 2))))

    if len(digit_groups) >= 2:
        # Les deux chiffres peuvent être séparés (notamment 9.1). Conserve la
        # paire la plus lumineuse tout en respectant l'ordre de l'afficheur.
        chosen = sorted(sorted(digit_groups, key=lambda group: group[4], reverse=True)[:2])
        decoded = [classify_range(left, right, top, bottom) for left, right, top, bottom, _ in chosen]
        if all(character for character, _ in decoded):
            return "".join(character for character, _ in decoded), min(confidence for _, confidence in decoded)

    # Le halo relie parfois les deux chiffres. Essaie plusieurs séparations :
    # leurs largeurs ne sont pas égales, surtout pour 4 et 2 à cette distance.
    start, end, top, bottom, _ = max(digit_groups or groups, key=lambda group: group[4])
    if end - start < 8:
        return None, 0.0
    # Quand le halo relie deux chiffres de même matrice, le découpage le plus
    # fiable est leur milieu géométrique. Choisir la séparation ayant la plus
    # forte confiance favorisait une portion du premier chiffre et transformait
    # clairement « 36 » en « 3A », puis en « 39 ».
    (first_start, first_end), (second_start, second_end) = _connected_digit_ranges(start, end)
    first = classify_range(first_start, first_end, top, bottom, allow_skinny_one=False)
    second = classify_range(second_start, second_end, top, bottom, allow_skinny_one=False)
    if not first[0] or not second[0]:
        return None, 0.0
    return first[0] + second[0], min(first[1], second[1])


def _connected_digit_ranges(start: int, end: int) -> tuple[tuple[int, int], tuple[int, int]]:
    """Sépare deux chiffres reliés sans attribuer leur pixel central aux deux."""
    split = (start + end + 1) // 2
    return (start, split - 1), (split, end)


def _crop(image: Image.Image, region: tuple[float, float, float, float]) -> Image.Image:
    width, height = image.size
    return image.crop((
        int(region[0] * width), int(region[1] * height),
        int(region[2] * width), int(region[3] * height),
    ))


def normalize_orp_text(value: str | None) -> str | None:
    """Corrige les ambiguïtés propres à l'afficheur numérique Micro Rx.

    La zone ORP ne peut afficher que deux chiffres. À longue distance, le halo
    relie le segment inférieur droit du 9 au segment central : sa géométrie est
    alors identique au A utilisé par l'afficheur pH pour l'alarme « AL ».
    Dans cette zone exclusivement numérique, A correspond donc sans ambiguïté
    à 9. La correction n'est volontairement jamais appliquée au pH.
    """
    if not value:
        return value
    return value.replace("A", "9")


def _quantile_image(images: list[Image.Image], quantile: float = 0.40) -> Image.Image:
    """Fusionne une rafale en rejetant les phases trop claires du multiplexage."""
    if not images:
        raise ValueError("Une image au minimum est requise")
    rgb_images = [image.convert("RGB") for image in images]
    size = rgb_images[0].size
    if any(image.size != size for image in rgb_images):
        raise ValueError("Toutes les images de la rafale doivent avoir la même taille")
    rank = max(0, min(len(rgb_images) - 1, round((len(rgb_images) - 1) * quantile)))
    samples = zip(*(image.tobytes() for image in rgb_images))
    data = bytes(sorted(values)[rank] for values in samples)
    return Image.frombytes("RGB", size, data)


def _vote_characters(values: list[str | None]) -> str | None:
    """Vote indépendamment sur chaque position d'un afficheur à deux chiffres."""
    candidates = [value for value in values if value and len(value) == 2]
    if not candidates:
        return None
    return "".join(Counter(value[index] for value in candidates).most_common(1)[0][0] for index in range(2))


def read_pool_images(
    images: list[Image.Image],
    *,
    mirror: bool = True,
    regions: dict[str, tuple[float, float, float, float]] | None = None,
) -> PoolReading:
    if not images:
        raise ValueError("Une image au minimum est requise")
    prepared = [
        image.transpose(Image.Transpose.FLIP_LEFT_RIGHT) if mirror else image
        for image in images
    ]
    regions = regions or DEFAULT_REGIONS
    ph_text, ph_confidence = _decode_two_characters(_quantile_image([
        _crop(image, regions["ph"]) for image in prepared
    ]))
    orp_decoded = [
        _decode_two_characters(_crop(image, regions["orp"]))
        for image in prepared
    ]
    orp_text = _vote_characters([normalize_orp_text(text) for text, _ in orp_decoded])
    orp_confidence = min(
        (confidence for _, confidence in orp_decoded if confidence > 0),
        default=0.0,
    )
    orp_text = normalize_orp_text(orp_text)
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


def read_pool_image(
    image: Image.Image,
    *,
    mirror: bool = True,
    regions: dict[str, tuple[float, float, float, float]] | None = None,
) -> PoolReading:
    return read_pool_images([image], mirror=mirror, regions=regions)


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
