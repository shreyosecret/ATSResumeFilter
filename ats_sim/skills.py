"""Curated skills taxonomy and term matching helpers."""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

from .data import DATA_DIR  # noqa: E402  (one place decides where the data lives)


@dataclass(frozen=True)
class Skill:
    name: str
    aliases: tuple[str, ...] = ()
    category: str = "general"
    broader: str | None = None

    @property
    def surface_forms(self) -> tuple[str, ...]:
        return (self.name, *self.aliases)


@dataclass
class SkillTaxonomy:
    skills: list[Skill] = field(default_factory=list)

    @classmethod
    def load(cls, path: str | Path | None = None) -> "SkillTaxonomy":
        path = Path(path) if path else DATA_DIR / "skills.json"
        raw = json.loads(Path(path).read_text(encoding="utf-8"))
        skills = [
            Skill(
                name=s["name"],
                aliases=tuple(s.get("aliases", [])),
                category=s.get("category", "general"),
                broader=s.get("broader"),
            )
            for s in raw["skills"]
        ]
        return cls(skills)

    def get(self, name: str) -> Skill | None:
        key = name.lower()
        for s in self.skills:
            if s.name.lower() == key:
                return s
        return None

    def canonical(self, surface: str) -> str | None:
        """Map any surface form (name or alias) to its canonical name."""
        for s in self.skills:
            for form in s.surface_forms:
                if _forms_equal(form, surface):
                    return s.name
        return None

    def find_all(self, text: str, use_aliases: bool = True) -> dict[str, list[str]]:
        """Return {canonical skill: [surface forms found]} for skills in text."""
        found: dict[str, list[str]] = {}
        for s in self.skills:
            forms = s.surface_forms if use_aliases else (s.name,)
            hits = [f for f in forms if contains_term(text, f)]
            if hits:
                found[s.name] = hits
        return found


@lru_cache(maxsize=1)
def default_taxonomy() -> SkillTaxonomy:
    return SkillTaxonomy.load()


def _forms_equal(a: str, b: str) -> bool:
    if len(a) <= 2 or len(b) <= 2:
        return a == b
    return a.lower() == b.lower()


@lru_cache(maxsize=4096)
def term_pattern(term: str) -> re.Pattern:
    """Regex that matches `term` as a whole token.

    Word boundaries are defined with look-arounds so terms such as "C++" or
    "GD&T" match correctly. Internal whitespace is flexible so a phrase that
    wrapped across a line break still matches. Terms of 1-2 characters are
    case-sensitive ("R", "ML") to avoid matching ordinary words.
    """
    parts = [re.escape(p) for p in term.split()]
    body = r"\s+".join(parts)
    flags = 0 if len(term) <= 2 else re.IGNORECASE
    return re.compile(rf"(?<![\w+#&]){body}(?![\w+#&])", flags)


def contains_term(text: str, term: str) -> bool:
    return term_pattern(term).search(text) is not None


def count_term(text: str, term: str) -> int:
    return len(term_pattern(term).findall(text))
