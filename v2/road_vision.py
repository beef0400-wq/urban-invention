# -*- coding: utf-8 -*-
"""Baccarat road screenshot parser (V2 P0).

Goal: recover a usable Banker/Player/Tie sequence from a screenshot without a paid
vision API. The parser is intentionally conservative: it returns accepted=False
when the geometry/color evidence is weak instead of inventing a road.
"""
from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import List, Dict, Tuple
import math

import cv2
import numpy as np


@dataclass
class RoadParseResult:
    accepted: bool
    confidence: float
    sequence: List[str]
    mode: str
    detected_symbols: int
    rows: int
    cols: int
    note: str

    def to_dict(self) -> Dict:
        return asdict(self)


def _decode(image_bytes: bytes):
    arr = np.frombuffer(image_bytes, dtype=np.uint8)
    img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
    if img is None:
        raise ValueError("無法讀取圖片")
    h, w = img.shape[:2]
    if h*w>20000000:
        raise ValueError("圖片尺寸過大，請裁切路單區")
    if w > 1600:
        scale = 1600.0 / w
        img = cv2.resize(img, (1600, max(1, int(h * scale))), interpolation=cv2.INTER_AREA)
    return img


def _color_masks(img):
    hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
    # Saturated road colors. UI gray/white is intentionally excluded.
    red1 = cv2.inRange(hsv, np.array([0, 75, 65]), np.array([12, 255, 255]))
    red2 = cv2.inRange(hsv, np.array([168, 75, 65]), np.array([180, 255, 255]))
    red = cv2.bitwise_or(red1, red2)
    blue = cv2.inRange(hsv, np.array([90, 65, 55]), np.array([138, 255, 255]))
    green = cv2.inRange(hsv, np.array([35, 70, 55]), np.array([88, 255, 255]))
    kernel = np.ones((2, 2), np.uint8)
    return {
        "莊": cv2.morphologyEx(red, cv2.MORPH_OPEN, kernel),
        "閒": cv2.morphologyEx(blue, cv2.MORPH_OPEN, kernel),
        "和": cv2.morphologyEx(green, cv2.MORPH_OPEN, kernel),
    }


def _symbols_from_mask(mask, label: str, img_area: int):
    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    out = []
    # Scale-aware broad filter; tiny text dots and giant UI panels are rejected.
    min_area = max(14, img_area * 0.000008)
    max_area = max(1100, img_area * 0.004)
    for c in contours:
        area = cv2.contourArea(c)
        if area < min_area or area > max_area:
            continue
        x, y, w, h = cv2.boundingRect(c)
        if w < 4 or h < 4:
            continue
        ratio = w / float(h)
        if not 0.42 <= ratio <= 2.35:
            continue
        peri = cv2.arcLength(c, True)
        circularity = 4 * math.pi * area / (peri * peri) if peri else 0
        # Outlined road circles can have modest circularity after thresholding.
        if circularity < 0.08:
            continue
        m = cv2.moments(c)
        if m["m00"]:
            cx = m["m10"] / m["m00"]
            cy = m["m01"] / m["m00"]
        else:
            cx, cy = x + w / 2, y + h / 2
        out.append({"x": float(cx), "y": float(cy), "w": w, "h": h, "area": area, "label": label})
    return out


def _dedupe(points):
    if not points:
        return []
    med = float(np.median([max(p["w"], p["h"]) for p in points]))
    tol = max(4.0, med * 0.35)
    kept = []
    # Prefer Banker/Player over green overlay when centers collide; ties in Big Road
    # are commonly an overlay and should not become an extra chronological cell.
    priority = {"莊": 3, "閒": 3, "和": 1}
    for p in sorted(points, key=lambda z: (priority[z["label"]], z["area"]), reverse=True):
        if any((p["x"]-q["x"])**2 + (p["y"]-q["y"])**2 <= tol*tol for q in kept):
            continue
        kept.append(p)
    return kept


def _components(points):
    if not points:
        return []
    size = float(np.median([max(p["w"], p["h"]) for p in points]))
    link = max(28.0, size * 4.2)
    n = len(points)
    seen = [False] * n
    comps = []
    for i in range(n):
        if seen[i]:
            continue
        stack = [i]
        seen[i] = True
        comp = []
        while stack:
            a = stack.pop()
            comp.append(points[a])
            pa = points[a]
            for j in range(n):
                if seen[j]:
                    continue
                pb = points[j]
                dx, dy = abs(pa["x"]-pb["x"]), abs(pa["y"]-pb["y"])
                # Prefer grid-neighbor-like linking over arbitrary diagonal UI grouping.
                if math.hypot(dx, dy) <= link and (dx <= link or dy <= link):
                    seen[j] = True
                    stack.append(j)
        comps.append(comp)
    return comps


def _cluster_axis(values: List[float], tol: float):
    if not values:
        return []
    groups = []
    for v in sorted(values):
        if not groups or abs(v - np.mean(groups[-1])) > tol:
            groups.append([v])
        else:
            groups[-1].append(v)
    return [float(np.mean(g)) for g in groups]


def _nearest_idx(v, centers):
    return int(np.argmin([abs(v-c) for c in centers]))


def _grid_candidate_score(comp):
    if len(comp) < 8:
        return -1, None
    symbol_size = float(np.median([max(p["w"], p["h"]) for p in comp]))
    tol = max(6.0, symbol_size * 0.75)
    xs = _cluster_axis([p["x"] for p in comp], tol)
    ys = _cluster_axis([p["y"] for p in comp], tol)
    if len(xs) < 2 or len(ys) < 2 or len(ys) > 12:
        return -1, None
    # Road boards usually have ~6 rows. Penalize wildly different geometry.
    row_penalty = abs(len(ys) - 6) * 0.8
    density = len(comp) / max(1, len(xs) * len(ys))
    color_count = len({p["label"] for p in comp if p["label"] in ("莊", "閒")})
    score = len(comp) + density * 12 + (6 if color_count >= 2 else -8) - row_penalty
    return score, (xs, ys, symbol_size)


def _reconstruct(comp, xs, ys):
    cells: Dict[Tuple[int, int], Dict] = {}
    for p in comp:
        ci, ri = _nearest_idx(p["x"], xs), _nearest_idx(p["y"], ys)
        k = (ci, ri)
        prev = cells.get(k)
        if prev is None or p["area"] > prev["area"]:
            cells[k] = p

    cols = []
    for ci in range(len(xs)):
        entries = [(ri, cells[(ci, ri)]) for ri in range(len(ys)) if (ci, ri) in cells]
        entries.sort(key=lambda z: z[0])
        if entries:
            cols.append(entries)

    if not cols:
        return [], "unknown", 0.0

    # Distinguish bead plate vs big road by within-column color consistency.
    consistency = []
    for entries in cols:
        labels = [p["label"] for _, p in entries if p["label"] in ("莊", "閒")]
        if labels:
            counts = {x: labels.count(x) for x in set(labels)}
            consistency.append(max(counts.values()) / len(labels))
    same_color_ratio = float(np.mean(consistency)) if consistency else 0.0

    if same_color_ratio >= 0.78:
        # Big Road: each column primarily represents one streak. Green is often tie overlay.
        seq = []
        for entries in cols:
            mains = [p["label"] for _, p in entries if p["label"] in ("莊", "閒")]
            if not mains:
                continue
            majority = max(set(mains), key=mains.count)
            seq.extend([majority] * len(mains))
        mode = "big-road"
        structural_conf = min(1.0, 0.58 + (same_color_ratio - 0.78) * 1.5)
    else:
        # Bead plate: chronological order is top-to-bottom, then left-to-right.
        seq = []
        for entries in cols:
            for _, p in entries:
                if p["label"] in ("莊", "閒", "和"):
                    seq.append(p["label"])
        mode = "bead-plate"
        structural_conf = min(1.0, 0.62 + max(0, 0.78 - same_color_ratio) * 0.6)

    return seq, mode, structural_conf


def parse_baccarat_road_image(image_bytes: bytes, min_main_results: int = 15) -> RoadParseResult:
    try:
        img = _decode(image_bytes)
    except Exception as e:
        return RoadParseResult(False, 0.0, [], "invalid", 0, 0, 0, f"圖片讀取失敗：{e}")

    h, w = img.shape[:2]
    masks = _color_masks(img)
    points = []
    # Green is parsed but treated conservatively because many UIs use green elsewhere.
    for label in ("莊", "閒", "和"):
        points.extend(_symbols_from_mask(masks[label], label, h*w))
    points = _dedupe(points)

    comps = _components(points)
    ranked = []
    for comp in comps:
        score, geom = _grid_candidate_score(comp)
        if geom:
            ranked.append((score, comp, geom))
    ranked.sort(key=lambda z: z[0], reverse=True)

    if not ranked:
        return RoadParseResult(False, 0.05, [], "none", len(points), 0, 0, "沒有找到可信的紅藍路單格線")

    _, comp, (xs, ys, _) = ranked[0]
    seq, mode, structural_conf = _reconstruct(comp, xs, ys)
    main_count = sum(1 for x in seq if x in ("莊", "閒"))

    count_conf = min(1.0, main_count / max(min_main_results, 1))
    color_balance = 1.0 if {"莊", "閒"}.issubset(set(seq)) else 0.45
    confidence = round(max(0.0, min(0.99, 0.45*structural_conf + 0.4*count_conf + 0.15*color_balance)), 2)

    # Big-road dragon tails and tie overlays cannot be chronologically recovered
    # by column majority. Never claim such reconstruction is reliable.
    ambiguous = mode == "big-road"
    if len(ranked)>1 and ranked[1][0] >= ranked[0][0]*0.85: ambiguous=True
    accepted = main_count >= min_main_results and confidence >= 0.80 and not ambiguous
    if ambiguous:
        note = "大路長龍／和局覆蓋或多路區塊有歧義；請截完整珠盤路，或一次貼上牌路。"
    elif accepted:
        note = f"已辨識 {main_count} 把莊閒主路；請先核對預覽，若有誤可快速補牌路。"
    elif main_count < min_main_results:
        note = f"只辨識到 {main_count} 把莊閒主路，至少需要 {min_main_results} 把。"
    else:
        note = "辨識信心不足，為避免誤判不會自動開始分析。請換一張完整路單截圖或使用快速貼上。"

    return RoadParseResult(accepted, confidence, seq, mode, len(comp), len(ys), len(xs), note)
