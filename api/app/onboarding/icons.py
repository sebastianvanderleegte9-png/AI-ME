"""Shared inline-SVG icon set for the site and dashboard (Components 14b/16), so both surfaces
read as one system instead of two different visual languages. Hand-authored, generic UI glyphs
(24x24, 1.8 stroke, round joins) — not a copy of any specific icon library or product's icon set."""
ICONS = {
    "grid": '<path d="M4 4h7v7H4zM13 4h7v7h-7zM4 13h7v7H4zM13 13h7v7h-7z" stroke="currentColor" stroke-width="1.8" fill="none" stroke-linejoin="round"/>',
    "trend": '<path d="M4 15l5-5 4 4 7-8M20 6h-4v4" stroke="currentColor" stroke-width="1.8" fill="none" stroke-linecap="round" stroke-linejoin="round"/>',
    "users": '<circle cx="9" cy="8" r="3.3" stroke="currentColor" stroke-width="1.8" fill="none"/><path d="M3.5 20c.6-3.8 3-5.6 5.5-5.6s4.9 1.8 5.5 5.6M15.5 14.6c2 .2 3.9 1.9 4.4 5.4M13.3 5.1a3.3 3.3 0 0 1 0 6.1" stroke="currentColor" stroke-width="1.8" fill="none" stroke-linecap="round"/>',
    "check": '<circle cx="12" cy="12" r="8.5" stroke="currentColor" stroke-width="1.8" fill="none"/><path d="M8.3 12.3l2.4 2.4 5-5" stroke="currentColor" stroke-width="1.8" fill="none" stroke-linecap="round" stroke-linejoin="round"/>',
    "file": '<path d="M7 3.5h7l4 4V20a.7.7 0 0 1-.7.7H7A.7.7 0 0 1 6.3 20V4.2A.7.7 0 0 1 7 3.5z" stroke="currentColor" stroke-width="1.8" fill="none" stroke-linejoin="round"/><path d="M14 3.5V8h4M9 12.5h6M9 16h6" stroke="currentColor" stroke-width="1.6" stroke-linecap="round"/>',
    "gauge": '<path d="M4 15a8 8 0 1 1 16 0" stroke="currentColor" stroke-width="1.8" fill="none" stroke-linecap="round"/><path d="M12 15l4-5.2" stroke="currentColor" stroke-width="1.8" fill="none" stroke-linecap="round"/><circle cx="12" cy="15" r="1.4" fill="currentColor"/>',
    "mail": '<rect x="3.3" y="5.5" width="17.4" height="13" rx="1.6" stroke="currentColor" stroke-width="1.8" fill="none"/><path d="M4 6.5l8 6.5 8-6.5" stroke="currentColor" stroke-width="1.8" fill="none" stroke-linecap="round" stroke-linejoin="round"/>',
    "cal": '<rect x="3.3" y="5" width="17.4" height="15.5" rx="1.8" stroke="currentColor" stroke-width="1.8" fill="none"/><path d="M3.3 9.5h17.4M8 3v4M16 3v4" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"/><path d="M9 14l2 2 4-4" stroke="currentColor" stroke-width="1.7" fill="none" stroke-linecap="round" stroke-linejoin="round"/>',
    "user": '<circle cx="12" cy="8.3" r="3.6" stroke="currentColor" stroke-width="1.8" fill="none"/><path d="M4.8 20c.9-4.4 3.6-6.5 7.2-6.5s6.3 2.1 7.2 6.5" stroke="currentColor" stroke-width="1.8" fill="none" stroke-linecap="round"/>',
    "search": '<circle cx="10.8" cy="10.8" r="6.3" stroke="currentColor" stroke-width="1.8" fill="none"/><path d="M20 20l-4.3-4.3" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"/>',
    "bell": '<path d="M6 9.5a6 6 0 0 1 12 0c0 4 1.5 5.5 1.5 5.5H4.5S6 13.5 6 9.5z" stroke="currentColor" stroke-width="1.8" fill="none" stroke-linejoin="round"/><path d="M10 18.5a2 2 0 0 0 4 0" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"/>',
    "arrow-right": '<path d="M4 12h15M13 6l6 6-6 6" stroke="currentColor" stroke-width="1.8" fill="none" stroke-linecap="round" stroke-linejoin="round"/>',
    "doc": '<path d="M6.5 3.5h8l3 3V20a.7.7 0 0 1-.7.7h-10a.7.7 0 0 1-.7-.7V4.2a.7.7 0 0 1 .4-.7z" stroke="currentColor" stroke-width="1.8" fill="none" stroke-linejoin="round"/><path d="M14 3.5V7h3.5" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"/>',
    "shield": '<path d="M12 3.5l7 2.6v5.4c0 5-3 7.8-7 9-4-1.2-7-4-7-9V6.1z" stroke="currentColor" stroke-width="1.8" fill="none" stroke-linejoin="round"/><path d="M8.7 12l2.3 2.3 4.3-4.6" stroke="currentColor" stroke-width="1.7" fill="none" stroke-linecap="round" stroke-linejoin="round"/>',
    "zap": '<path d="M13 2.5L5 14h6l-1 7.5L19 10h-6z" stroke="currentColor" stroke-width="1.7" fill="none" stroke-linejoin="round"/>',
    "target": '<circle cx="12" cy="12" r="8.2" stroke="currentColor" stroke-width="1.6" fill="none"/><circle cx="12" cy="12" r="4.6" stroke="currentColor" stroke-width="1.6" fill="none"/><circle cx="12" cy="12" r="1.2" fill="currentColor"/>',
    "layers": '<path d="M12 3.5l8.5 4.4L12 12.3 3.5 7.9z" stroke="currentColor" stroke-width="1.7" fill="none" stroke-linejoin="round"/><path d="M3.5 12.1l8.5 4.4 8.5-4.4M3.5 16.3l8.5 4.4 8.5-4.4" stroke="currentColor" stroke-width="1.7" fill="none" stroke-linejoin="round" stroke-linecap="round"/>',
    "wand": '<path d="M4 20l10-10M14.5 3.5l1 2 2 1-2 1-1 2-1-2-2-1 2-1z" stroke="currentColor" stroke-width="1.6" fill="none" stroke-linejoin="round" stroke-linecap="round"/><path d="M17.5 12l.7 1.5 1.5.7-1.5.7-.7 1.5-.7-1.5-1.5-.7 1.5-.7z" stroke="currentColor" stroke-width="1.4" fill="none" stroke-linejoin="round"/>',
    "compass": '<circle cx="12" cy="12" r="8.5" stroke="currentColor" stroke-width="1.7" fill="none"/><path d="M15 9l-2 6-4 2 2-6z" stroke="currentColor" stroke-width="1.5" fill="none" stroke-linejoin="round"/>',
}


def icon(name: str, size: int = 17) -> str:
    return f'<svg viewBox="0 0 24 24" width="{size}" height="{size}" fill="none">{ICONS[name]}</svg>'
