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

MINIMUM_READING_CONFIDENCE = 0.55

# Sur le cadrage définitif de l'AstralPool Micro pH, le balayage de l'afficheur
# peut remplacer la barre basse du L par les deux segments droits et fermer le
# A. La rafale montre alors respectivement 1 et 9. Ces variantes ne sont
# acceptées que sur l'afficheur pH ; la zone ORP reste strictement numérique.
PH_ALARM_ALIASES = {"AL", "0L", "8L", "A1"}

NUMERIC_SEGMENTS = {
    character: segments
    for segments, character in SEGMENTS.items()
    if character.isdigit()
}

TEMPORAL_PATCHES = {
    # Les horizontales sont échantillonnées sur leur moitié gauche : à cette
    # distance, le halo des segments verticaux droits déborde jusqu'au centre.
    "a": (0.18, 0.08, 0.48, 0.20),
    "b": (0.80, 0.25, 0.98, 0.42),
    "c": (0.80, 0.60, 0.98, 0.77),
    "d": (0.18, 0.82, 0.48, 0.94),
    "e": (0.02, 0.60, 0.20, 0.77),
    "f": (0.02, 0.25, 0.20, 0.42),
    "g": (0.18, 0.46, 0.48, 0.58),
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


def _profile_character(
    images: list[Image.Image],
    cell: tuple[int, int, int, int],
) -> dict[str, float]:
    """Mesure les sept segments en moyennant toutes les phases de la rafale."""
    left, right, top, bottom = cell
    rgb_images = [image.convert("RGB") for image in images]
    pixels = [image.load() for image in rgb_images]
    scores: dict[str, float] = {}
    for name, (x0, y0, x1, y1) in TEMPORAL_PATCHES.items():
        patch_left = left + int((right - left) * x0)
        patch_right = max(patch_left + 1, left + int((right - left) * x1))
        patch_top = top + int((bottom - top) * y0)
        patch_bottom = max(patch_top + 1, top + int((bottom - top) * y1))
        strengths = []
        for image_pixels in pixels:
            for y in range(patch_top, patch_bottom):
                for x in range(patch_left, patch_right):
                    red, green, blue = image_pixels[x, y]
                    strengths.append(max(0, red - max(green, blue)))
        scores[name] = sum(strengths) / max(1, len(strengths))
    strongest = max(scores.values(), default=0.0)
    if strongest:
        scores = {name: value / strongest for name, value in scores.items()}
    return scores


def _classify_temporal_profile(scores: dict[str, float]) -> tuple[str | None, float]:
    """Classe un profil sept segments déformé par le balayage de l'afficheur."""
    if not scores or max(scores.values(), default=0.0) <= 0:
        return None, 0.0

    # Cas très caractéristiques observés sur les rafales réelles. Ces règles
    # utilisent des rapports de segments et restent indépendantes de la valeur.
    if (
        scores["a"] > 0.85
        and scores["d"] < 0.48
        and scores["e"] < 0.48
        and scores["c"] < 0.60
    ):
        return "7", 0.72
    if (
        scores["b"] < 0.25
        and scores["e"] > 0.65
        and scores["f"] > 0.65
        and scores["g"] > 0.75
    ):
        return "6", 0.72
    if (
        scores["e"] > 0.60
        and scores["f"] > 0.60
        and scores["g"] > 0.75
        and scores["c"] > scores["b"] + 0.20
    ):
        return "6", 0.68
    if (
        scores["a"] < 0.35
        and scores["d"] < 0.35
        and scores["b"] > 0.50
        and scores["c"] > 0.45
        and scores["g"] > 0.75
    ):
        return "4", 0.72
    if (
        scores["g"] > 0.70
        and scores["b"] + scores["c"] > scores["e"] + scores["f"] + 0.12
    ):
        return "3", 0.72

    # Ajuste pour chaque chiffre deux niveaux (segment éteint/allumé), puis
    # compare l'erreur résiduelle. Cela absorbe les variations de luminosité.
    candidates = []
    segment_names = "abcdefg"
    for character, active in NUMERIC_SEGMENTS.items():
        on = [scores[name] for name in segment_names if name in active]
        off = [scores[name] for name in segment_names if name not in active]
        if not off:
            continue
        on_mean = sum(on) / len(on)
        off_mean = sum(off) / len(off)
        contrast = on_mean - off_mean
        if contrast <= 0:
            continue
        error = (
            sum((value - on_mean) ** 2 for value in on)
            + sum((value - off_mean) ** 2 for value in off)
        ) / len(segment_names)
        candidates.append((error, character, contrast))
    candidates.sort()
    if not candidates:
        return None, 0.0
    best_error, character, contrast = candidates[0]
    gap = candidates[1][0] - best_error if len(candidates) > 1 else 1.0
    if best_error > 0.08 or contrast < 0.10 or gap < 0.008:
        return None, 0.0
    return character, min(0.70, 0.58 + gap + contrast * 0.15)


def _decode_temporal_characters(images: list[Image.Image]) -> tuple[str | None, float]:
    """Localise et lit deux chiffres sur toutes les phases de neuf images."""
    if not images:
        return None, 0.0
    masks = [_red_mask(image, threshold=165) for image in images]
    height = len(masks[0])
    width = len(masks[0][0]) if height else 0
    columns = [
        sum(mask[y][x] for mask in masks for y in range(height))
        for x in range(width)
    ]
    # Le voyant ALARM forme un petit groupe à gauche. Les deux chiffres sont
    # les deux groupes larges et lumineux de la zone d'affichage.
    groups = [group for group in _runs(columns, minimum=5) if group[1] - group[0] >= 5]
    groups = sorted(sorted(
        groups,
        key=lambda group: sum(columns[group[0]:group[1]]),
        reverse=True,
    )[:2])
    if len(groups) != 2:
        return None, 0.0

    rows = [
        sum(
            mask[y][x]
            for mask in masks
            for x in range(groups[0][0], groups[1][1])
        )
        for y in range(height)
    ]
    row_groups = _runs(rows, minimum=5)
    if not row_groups:
        return None, 0.0
    bright_top, bright_bottom = max(row_groups, key=lambda group: group[1] - group[0])
    top = max(0, bright_top - 3)
    bottom = min(height, bright_bottom + 4)
    centers = [(start + end - 1) / 2 for start, end in groups]
    pitch = centers[1] - centers[0]
    half_width = max(6, round(pitch * 0.50))

    decoded = []
    for center in centers:
        left = max(0, round(center - half_width))
        right = min(width, round(center + half_width + 1))
        decoded.append(_classify_temporal_profile(
            _profile_character(images, (left, right, top, bottom))
        ))
    if not all(character for character, _ in decoded):
        return None, 0.0
    return "".join(character for character, _ in decoded), min(
        confidence for _, confidence in decoded
    )


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


def normalize_ph_text(value: str | None) -> str | None:
    """Normalise les formes prises par ``AL`` sur l'afficheur pH multiplexé."""
    if not value:
        return value
    return "AL" if value in PH_ALARM_ALIASES else value


def _prefer_frame_consensus(
    primary_text: str | None,
    primary_confidence: float,
    voted_text: str | None,
    voted_confidence: float,
) -> tuple[str | None, float]:
    """Préfère un vote net des images à une fusion temporelle contradictoire.

    La fusion est utile lorsque les segments sont multiplexés, mais son profil
    peut confondre 6/9 avec 3. Un même texte retrouvé sur au moins 80 % des
    images constitue alors une preuve plus forte.
    """
    if voted_text and voted_confidence >= MINIMUM_READING_CONFIDENCE:
        if not primary_text or voted_text != primary_text:
            return voted_text, voted_confidence
        return voted_text, max(primary_confidence, voted_confidence)
    return primary_text, primary_confidence


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


def _vote_characters_with_confidence(values: list[str | None]) -> tuple[str | None, float]:
    """Vote sur une rafale et exige un accord net avant de lui faire confiance."""
    candidates = [value for value in values if value and len(value) == 2]
    if len(candidates) < 5:
        return None, 0.0
    winners = [
        Counter(value[index] for value in candidates).most_common(1)[0]
        for index in range(2)
    ]
    consensus = min(count / len(candidates) for _, count in winners)
    text = "".join(character for character, _ in winners)
    # Sur le Micro Rx, le balayage transforme ponctuellement un 6 en 2, 3 ou
    # 8. Un accord d'au moins 60 % sur chaque position est déjà nettement plus
    # fiable que la fusion temporelle, qui peut alors reconstruire deux 3.
    if consensus < 0.60:
        return text, 0.45
    return text, min(0.85, 0.58 + (consensus - 0.60) * 0.60)


def _detect_ph_alarm(images: list[Image.Image]) -> tuple[bool, float]:
    """Repère ``AL`` dans les phases complètes de l'afficheur multiplexé.

    Sur le Micro pH filmé par l'ESP, plusieurs images de la rafale ne montrent
    que le point décimal. Les images complètes relient en revanche le A et le L
    par un léger halo horizontal. Leur séparation n'est pas centrée : le A est
    sensiblement plus large que le L. On essaie donc plusieurs coupures, puis on
    exige au moins deux phases concordantes pour éviter un faux positif.
    """
    matches = 0
    checked = 0
    confidences: list[float] = []
    for image in images:
        mask = _red_mask(image, threshold=75)
        height = len(mask)
        width = len(mask[0]) if height else 0
        columns = [sum(mask[y][x] for y in range(height)) for x in range(width)]
        groups = sorted(
            _runs(columns, minimum=1),
            key=lambda group: sum(columns[group[0]:group[1]]),
            reverse=True,
        )
        frame_matched = False
        for start, end in groups:
            if end - start < 20:
                continue
            lit_rows = [
                y for y in range(height)
                if any(mask[y][x] for x in range(start, end))
            ]
            if not lit_rows or max(lit_rows) - min(lit_rows) < 12:
                continue
            checked += 1
            top = max(0, min(lit_rows) - 3)
            bottom = min(height, max(lit_rows) + 4)
            span = end - start
            for ratio in (0.62, 0.66, 0.70, 0.74, 0.76, 0.78, 0.80):
                split = start + round(span * ratio)
                first = _classify_character(image.crop((
                    max(0, start - 2), top, min(width, split + 1), bottom,
                )))
                second = _classify_character(image.crop((
                    max(0, split - 1), top, min(width, end + 2), bottom,
                )))
                if (
                    first[0] == "A"
                    and second[0] == "L"
                    and first[1] >= MINIMUM_READING_CONFIDENCE
                    and second[1] >= MINIMUM_READING_CONFIDENCE
                ):
                    matches += 1
                    confidences.append(min(first[1], second[1]))
                    frame_matched = True
                    break
            if frame_matched:
                break
    if matches < 2:
        return False, 0.0
    agreement = matches / max(2, checked)
    confidence = min(0.90, max(0.70, min(confidences) + agreement * 0.15))
    return True, confidence


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
    ph_crops = [_crop(image, regions["ph"]) for image in prepared]
    ph_text, ph_confidence = _decode_two_characters(_quantile_image(ph_crops))
    ph_frames = [_decode_two_characters(image) for image in ph_crops]
    ph_voted, ph_vote_confidence = _vote_characters_with_confidence(
        [normalize_ph_text(text) for text, _ in ph_frames]
    )
    ph_text = normalize_ph_text(ph_text)
    ph_voted = normalize_ph_text(ph_voted)
    ph_text, ph_confidence = _prefer_frame_consensus(
        ph_text,
        ph_confidence,
        ph_voted,
        ph_vote_confidence,
    )
    if ph_voted and ph_voted.isdigit() and 40 <= int(ph_voted) <= 100:
        # Le premier chiffre du pH alterne parfois entre 9 et 8 suivant la
        # phase, alors que la pluralité des neuf images conserve bien 9.1.
        ph_text = ph_voted
        ph_confidence = max(ph_confidence, 0.58)
    ph_alarm, ph_alarm_confidence = _detect_ph_alarm(ph_crops)
    if ph_alarm:
        ph_text = "AL"
        ph_confidence = max(ph_confidence, ph_alarm_confidence)
    orp_crops = [_crop(image, regions["orp"]) for image in prepared]
    orp_text, orp_confidence = _decode_temporal_characters(orp_crops)
    orp_decoded = [_decode_two_characters(image) for image in orp_crops]
    orp_voted, orp_vote_confidence = _vote_characters_with_confidence(
        [normalize_orp_text(text) for text, _ in orp_decoded]
    )
    orp_text, orp_confidence = _prefer_frame_consensus(
        normalize_orp_text(orp_text),
        orp_confidence,
        normalize_orp_text(orp_voted),
        orp_vote_confidence,
    )
    orp_text = normalize_orp_text(orp_text)
    # À cette distance, le halo peut fermer les deux ouvertures du A et le faire
    # ressembler à 0 ou 8. Un second caractère L rend néanmoins l'état non ambigu.
    ph_text = normalize_ph_text(ph_text)
    # Une correspondance approximative vaut 0,45. À la distance actuelle, le
    # balayage de l'afficheur peut alors transformer visuellement 37 en 23.
    # Ne publie jamais cette estimation : conserver une ancienne mesure sûre
    # ou afficher « indisponible » est préférable à une valeur chimique fausse.
    if ph_text != "AL" and ph_confidence < MINIMUM_READING_CONFIDENCE:
        ph_text = None
        ph_confidence = 0.0
    if orp_confidence < MINIMUM_READING_CONFIDENCE:
        orp_text = None
        orp_confidence = 0.0
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
    """Confirme séparément les deux afficheurs et l'état d'alarme.

    Les afficheurs sont multiplexés et une valeur ORP peut varier pendant que
    l'afficheur pH montre nettement ``AL``. Confirmer le triplet complet
    (pH, ORP, alarme) bloquait alors l'alarme et conservait des valeurs anciennes.
    """
    recent = history[-3:]
    if len(recent) < minimum:
        return None

    alarm_values = [bool(row.get("alarm")) for row in recent]
    alarm = Counter(alarm_values).most_common(1)[0]
    if alarm[1] < minimum:
        return None

    def confirmed_value(key: str) -> Any:
        values = [row.get(key) for row in recent if row.get(key) is not None]
        if not values:
            return None
        value, count = Counter(values).most_common(1)[0]
        return value if count >= minimum else None

    ph = None if alarm[0] else confirmed_value("ph")
    orp_mv = confirmed_value("orp_mv")
    if not alarm[0] and ph is None and orp_mv is None:
        return None

    matching_alarm = [row for row in recent if bool(row.get("alarm")) == alarm[0]]
    latest = matching_alarm[-1]
    return PoolReading(
        ph=ph,
        orp_mv=orp_mv,
        alarm=alarm[0],
        ph_text="AL" if alarm[0] else (
            latest.get("ph_text") if latest.get("ph") == ph else None
        ),
        orp_text=next((
            row.get("orp_text")
            for row in reversed(recent)
            if row.get("orp_mv") == orp_mv
        ), None),
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
