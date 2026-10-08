"""Plain data containers shared across the pipeline."""
from __future__ import annotations

from dataclasses import asdict, dataclass, field


@dataclass
class ExperienceEntry:
    title: str | None = None
    company: str | None = None
    dates: str | None = None


@dataclass
class ParsedResume:
    """What a naive ATS parser extracts from a resume file."""

    source: str
    raw_text: str
    sections: dict[str, str] = field(default_factory=dict)
    name: str | None = None
    email: str | None = None
    phone: str | None = None
    degree_level: str | None = None
    field_of_study: str | None = None
    school: str | None = None
    grad_date: str | None = None  # YYYY-MM
    gpa: float | None = None
    skills: list[str] = field(default_factory=list)  # items listed under a skills heading
    experience: list[ExperienceEntry] = field(default_factory=list)

    def fields(self) -> dict:
        d = asdict(self)
        d.pop("raw_text")
        d.pop("sections")
        return d


@dataclass
class SkillRequirement:
    name: str  # canonical name (or the noun phrase itself for uncurated terms)
    surface: str  # the exact wording used in the posting
    level: str  # "required" | "preferred"
    curated: bool = True
    group: str | None = None  # requirements sharing a group are alternatives ("Python or MATLAB")


@dataclass
class Knockouts:
    grad_window: tuple[str, str] | None = None  # inclusive (YYYY-MM, YYYY-MM)
    min_gpa: float | None = None
    degree_fields: list[str] | None = None  # accepted fields of study
    min_degree_level: str | None = None  # "BS" | "MS" | "PHD"
    require_work_authorization: bool = False
    no_sponsorship: bool = False


@dataclass
class JobPosting:
    id: str
    title: str
    text: str
    knockouts: Knockouts = field(default_factory=Knockouts)
    rules_found: list = field(default_factory=list)  # for a pasted posting: each rule and the sentence it came from


@dataclass
class JobAnalysis:
    job: JobPosting
    requirements: list[SkillRequirement]
    sections: dict[str, str]
    requirement_lines: list[str]

    @property
    def required(self) -> list[SkillRequirement]:
        return [r for r in self.requirements if r.level == "required"]

    @property
    def preferred(self) -> list[SkillRequirement]:
        return [r for r in self.requirements if r.level == "preferred"]
