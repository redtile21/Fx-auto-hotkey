"""Colour schemes (pure Python, no Qt). 5 schemes x {dark, light} = 10 themes."""
from __future__ import annotations

W, K = "#FFFFFF", "#000000"

SCHEMES = {
    "aurora":  dict(name="Aurora",  sub="Purple \u00b7 Blue",    tint="#7C3AED",
                    dark=("#7C3AED", "#3B82F6"), light=("#7C3AED", "#3B82F6")),
    "citrus":  dict(name="Citrus",  sub="Green \u00b7 Orange",   tint="#16A34A",
                    dark=("#16A34A", "#F97316"), light=("#15803D", "#EA580C")),
    "mono":    dict(name="Mono",    sub="White \u00b7 Black",    tint="#808080",
                    dark=("#FFFFFF", "#9CA3AF"), light=("#0F172A", "#64748B")),
    "crimson": dict(name="Crimson", sub="Blue \u00b7 Red",       tint="#2563EB",
                    dark=("#3B82F6", "#EF4444"), light=("#2563EB", "#DC2626")),
    "neon":    dict(name="Neon",    sub="Cyan \u00b7 Magenta",   tint="#0891B2",
                    dark=("#0891B2", "#D946EF"), light=("#0E7490", "#C026D3")),
}
ORDER = ["aurora", "citrus", "mono", "crimson", "neon"]


def _rgb(h: str):
    h = h.lstrip("#")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def _hex(rgb) -> str:
    return "#%02X%02X%02X" % tuple(max(0, min(255, round(v))) for v in rgb)


def mix(a: str, b: str, t: float) -> str:
    ra, rb = _rgb(a), _rgb(b)
    return _hex(tuple(ra[i] + (rb[i] - ra[i]) * t for i in range(3)))


def rgba(h: str, alpha: int) -> str:
    r, g, b = _rgb(h)
    return f"rgba({r},{g},{b},{alpha})"


def lum(h: str) -> float:
    def f(v):
        v /= 255
        return v / 12.92 if v <= 0.03928 else ((v + 0.055) / 1.055) ** 2.4
    r, g, b = _rgb(h)
    return 0.2126 * f(r) + 0.7152 * f(g) + 0.0722 * f(b)


def contrast(a: str, b: str) -> float:
    la, lb = lum(a), lum(b)
    hi, lo = max(la, lb), min(la, lb)
    return (hi + 0.05) / (lo + 0.05)


def _hi(c: str) -> str:
    return mix(c, W, 0.18) if lum(c) < 0.6 else mix(c, K, 0.10)


def on_accent(a: str, b: str) -> str:
    """Text colour for the gradient: white unless it would be hard to read."""
    return W if min(contrast(W, a), contrast(W, b)) >= 2.3 else "#101014"


def build(mode: str, scheme: str) -> dict:
    s = SCHEMES.get(scheme) or SCHEMES["aurora"]
    dark = mode == "dark"
    a, b = s["dark" if dark else "light"]
    T = s["tint"]
    if dark:
        # Deeper, more muted surfaces — still tinted, but less “bright”.
        # Accent gradients (icons / primary buttons) stay fully saturated.
        c = dict(bg=mix(T, K, .945), bg2=mix(T, K, .92), surface=mix(T, K, .88),
                 surface2=mix(T, K, .80), border=mix(T, K, .68), hover=mix(T, K, .76),
                 side_a=mix(T, K, .86), text=mix(T, W, .90), muted=mix(T, W, .48),
                 danger="#F43F5E", ok="#22C55E",
                 gt_a=mix(a, W, .22), gt_b=mix(b, W, .22))
        c["track"] = c["border"]
        c.update(sel_a=rgba(a, 95), sel_b=rgba(b, 75), sel=rgba(a, 55), alt=rgba(a, 10))
    else:
        c = dict(bg=mix(T, W, .94), bg2=mix(T, W, .90), surface=W,
                 surface2=mix(T, W, .92), border=mix(T, W, .76), hover=mix(T, W, .86),
                 side_a=mix(T, W, .84), text=mix(T, K, .78), muted=mix(T, K, .42),
                 danger="#E11D48", ok="#16A34A",
                 gt_a=mix(a, K, .08), gt_b=mix(b, K, .08))
        c["track"] = mix(T, W, .68)
        c.update(sel_a=rgba(a, 70), sel_b=rgba(b, 55), sel=rgba(a, 40), alt=rgba(a, 10))
    c["side_b"] = c["bg"]
    c.update(grad_a=a, grad_b=b, grad_a_hi=_hi(a), grad_b_hi=_hi(b))
    oa = on_accent(a, b)
    c.update(on_accent=oa, on_soft=rgba(oa, 205), box=rgba(oa, 46))
    return c
