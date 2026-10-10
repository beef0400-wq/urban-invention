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
    kernel = np.ones((3, 3), np.uint8)
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
    max_area = max(1100, img_area * 0.025)
    for c in contours:
        x, y, w, h = cv2.boundingRect(c)
        # JPEG compression can connect adjacent same-colour disks through a
        # narrow bridge. Split only at a low-ink seam, never a solid panel.
        vertical = h >= w*1.65 and w >= 8
        horizontal = w >= h*1.65 and h >= 8
        if vertical or horizontal:
            part = mask[y:y+h,x:x+w]
            axis = 0 if vertical else 1
            length, diameter = (h,w) if vertical else (w,h)
            count = round(length/diameter)
            profile = np.count_nonzero(part, axis=1 if vertical else 0)
            cuts = [0]
            for i in range(1,count):
                expected = round(length*i/count)
                radius = max(2,round(diameter*.15))
                low,high=max(cuts[-1]+1,expected-radius),min(length,expected+radius+1)
                cut = low+int(np.argmin(profile[low:high]))
                if profile[cut] > diameter*.22:
                    cuts=[];break
                cuts.append(cut)
            if cuts:
                cuts.append(length)
                for low,high in zip(cuts,cuts[1:]):
                    tile=part[low:high,:] if vertical else part[:,low:high]
                    for p in _symbols_from_mask(tile,label,img_area):
                        ox,oy=x+(0 if vertical else low),y+(low if vertical else 0)
                        for key in ('x','bx'):p[key]+=ox
                        for key in ('y','by'):p[key]+=oy
                        out.append(p)
                continue
        area = cv2.contourArea(c)
        if area < min_area or area > max_area:
            continue
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
        out.append({"x": float(cx), "y": float(cy), "bx": x+w/2, "by": y+h/2, "w": w, "h": h, "area": area, "label": label})
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


def _bead_candidates(points, width, height, masks):
    """Separate symbol scales before grouping; never merge the derived roads.

    Only a six-row, regularly spaced, gap-free column-major grid is usable.
    Large pair dots are excluded by scale; use bounding-box centers because pair
    overlays shift contour moments away from the actual cell center.
    """
    square = [p for p in points if .78 <= p['w']/p['h'] <= 1.28]
    candidates = []
    seen = set()
    for seed in square:
        size = max(seed['w'], seed['h'])
        group = [dict(p, x=p.get('bx',p['x']), y=p.get('by',p['y'])) for p in square
                 if .86*size <= max(p['w'], p['h']) <= 1.16*size]
        for comp in _components_at_distance(group, size*2.4):
            key = tuple(sorted((round(p['x']), round(p['y'])) for p in comp))
            if key in seen or len(comp) < 15:
                continue
            seen.add(key)
            tol = max(2, size*.23)
            xs = _cluster_axis([p['x'] for p in comp], tol)
            ys = _cluster_axis([p['y'] for p in comp], tol)
            if len(ys) != 6 or len(xs) < 3:
                continue
            dx, dy = np.diff(xs), np.diff(ys)
            if any(np.max(d)/np.min(d) > 1.18 for d in (dx, dy)):
                continue
            if not (.85*size <= np.median(dx) <= 2.3*size and
                    .85*size <= np.median(dy) <= 2.3*size):
                continue
            cells = {}
            bad = False
            for p in comp:
                ci, ri = _nearest_idx(p['x'], xs), _nearest_idx(p['y'], ys)
                if abs(p['x']-xs[ci]) > tol or abs(p['y']-ys[ri]) > tol or (ci, ri) in cells:
                    bad = True; break
                # A clipped cell must not be inferred from a partial circle.
                if (p['x']-p['w']/2 < 1 or p['x']+p['w']/2 > width-1 or
                    p['y']-p['h']/2 < 1 or p['y']+p['h']/2 > height-1):
                    bad = True; break
                cells[(ci, ri)] = p
            if bad:
                continue
            # Read each disk from pixels, including compressed disks joined to
            # neighbours. Never fill an empty/unclear cell from its neighbours.
            seq=[]; ended=False
            radius=max(3,round(size*.43))
            yy,xx=np.ogrid[-radius:radius+1,-radius:radius+1]
            disk=xx*xx+yy*yy<=radius*radius
            for ci,cx in enumerate(xs):
                for ri,cy in enumerate(ys):
                    ix,iy=round(cx),round(cy)
                    if ix-radius<0 or iy-radius<0 or ix+radius>=width or iy+radius>=height:
                        bad=True;break
                    coverage={label:np.count_nonzero(mask[iy-radius:iy+radius+1,ix-radius:ix+radius+1][disk])/np.count_nonzero(disk)
                              for label,mask in masks.items()}
                    ranked=sorted(coverage,key=coverage.get,reverse=True)
                    if coverage[ranked[0]]<.38:
                        ended=True
                        continue
                    if ended or coverage[ranked[1]]>.20:
                        bad=True;break
                    seq.append(ranked[0])
                if bad:break
            if bad or len(seq)<15 or len(seq)<=6*(len(xs)-1):
                continue
            _, mode, _ = _reconstruct(comp, xs, ys)
            if mode != 'bead-plate':
                continue
            if any(seq==old_seq and len(xs)==len(old_xs) and
                   max(abs(a-b) for a,b in zip(xs,old_xs))<tol and
                   max(abs(a-b) for a,b in zip(ys,old_ys))<tol
                   for old_seq,_,old_xs,old_ys in candidates):
                continue
            candidates.append((seq, comp, xs, ys))
    return candidates


def _components_at_distance(points, distance):
    remaining = set(range(len(points)))
    out = []
    while remaining:
        stack = [remaining.pop()]; comp = []
        while stack:
            i = stack.pop(); p = points[i]; comp.append(p)
            nearby = [j for j in remaining if math.hypot(p['x']-points[j]['x'], p['y']-points[j]['y']) <= distance]
            remaining.difference_update(nearby); stack.extend(nearby)
        out.append(comp)
    return out


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

    beads = _bead_candidates(points, w, h, masks)
    if len(beads) == 1:
        seq, comp, xs, ys = beads[0]
        main_count = len(seq)-seq.count('和')
        accepted = main_count >= min_main_results
        note = (f"珠盤路 {len(seq)} 局：莊 {seq.count('莊')}、閒 {seq.count('閒')}、和 {seq.count('和')}。請核對總局數與順序，再按確認開始。" if accepted
                else f"珠盤路只有 {main_count} 把莊閒，至少需要 {min_main_results} 把。")
        return RoadParseResult(accepted, .90 if accepted else .5, seq, 'bead-plate', len(seq), 6, len(xs), note)
    if len(beads) > 1:
        return RoadParseResult(False, 0, [], 'ambiguous', 0, 0, 0,
                               '找到多份珠盤路，無法確定目前桌號。請只截目前桌的完整珠盤路。')

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
    # The permissive legacy detector is diagnostic only. It may combine grids or
    # silently close holes, so it must never stage a playable sequence.
    accepted = False
    confidence = min(confidence, .49)
    if ambiguous:
        note = "大路長龍／和局覆蓋或多路區塊有歧義；請截完整珠盤路，或一次貼上牌路。"
    elif accepted:
        note = f"已辨識 {main_count} 把莊閒主路；請先核對預覽，若有誤可快速補牌路。"
    elif main_count < min_main_results:
        note = f"只辨識到 {main_count} 把莊閒主路，至少需要 {min_main_results} 把。"
    else:
        note = "珠盤路格數、間距或順序無法完整核對。請傳完整六列珠盤路，或使用手動輸入。"

    return RoadParseResult(accepted, confidence, seq, mode, len(comp), len(ys), len(xs), note)
