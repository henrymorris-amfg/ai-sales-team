from __future__ import annotations

from dataclasses import dataclass, field
from typing import List

NEGATIVE_SIGNALS = {
    "sheet metal": -30,
    "fabrication": -18,
    "laser cutting": -28,
    "waterjet": -28,
    "stamping": -30,
    "roll forming": -30,
    "forging": -30,
    "casting": -24,
    "tool and die": -20,
    "no in-house": -30,
    "not accepting rfq": -25,
    "swiss screw": -22,
    "extrusion": -18,
    "jigs": -16,
    "fixtures": -16,
    "2d drawings": -18,
    "instant quote": -18,
    "additive manufacturing": -10,
    "3d printing": -10,
    "molding": -12,
    "consultancy": -12,
}

POSITIVE_SIGNALS = {
    "precision machining": 18,
    "cnc machining": 18,
    "5-axis": 14,
    "5 axis": 14,
    "build to print": 16,
    "request a quote": 14,
    "rfq": 14,
    "high mix": 12,
    "low volume": 12,
    "cnc milling": 12,
    "cnc turning": 12,
    "mill-turn": 12,
    "mill turn": 12,
    "billet": 10,
    "blank": 8,
    "subcontract manufacturing": 14,
    "cad": 8,
    "engineering drawings": 8,
    "quote": 8,
    "aerospace": 8,
    "medical": 8,
    "defense": 8,
    "industrial": 5,
    "iso 9001": 6,
    "as9100": 8,
    "mes": 5,
    "erp": 5,
    "estimating": 8,
    "production planning": 8,
}


@dataclass
class WebsiteReviewResult:
    fit_signals: List[str] = field(default_factory=list)
    disqualify_signals: List[str] = field(default_factory=list)
    recommendation: str = "needs_review"
    confidence: float = 0.0
    score: int = 50
    conflict_flag: bool = False


def review_text(text: str) -> WebsiteReviewResult:
    lower = (text or "").lower()
    fit_hits: List[str] = []
    disqualify_hits: List[str] = []
    score = 50

    for signal, points in POSITIVE_SIGNALS.items():
        if signal in lower:
            fit_hits.append(signal)
            score += points

    for signal, points in NEGATIVE_SIGNALS.items():
        if signal in lower:
            disqualify_hits.append(signal)
            score += points

    conflict_flag = bool(fit_hits and disqualify_hits)
    score = max(0, min(100, score))

    if score <= 20 and not conflict_flag:
        recommendation = "archive_disqualified"
    elif score >= 80:
        recommendation = "very_good_fit"
    elif score >= 60:
        recommendation = "good_fit"
    else:
        recommendation = "needs_review"

    confidence = 0.45 + (abs(score - 50) / 100)
    if conflict_flag:
        confidence -= 0.1
    confidence = max(0.25, min(0.98, confidence))

    return WebsiteReviewResult(
        fit_signals=fit_hits,
        disqualify_signals=disqualify_hits,
        recommendation=recommendation,
        confidence=round(confidence, 2),
        score=score,
        conflict_flag=conflict_flag,
    )
