"""Recruiter-style Boolean search: (Python OR MATLAB) AND "GMP" NOT intern.

Grammar (case-insensitive operators, implicit AND between adjacent terms):
    query  := or
    or     := and ("OR" and)*
    and    := unary (["AND"] unary)*
    unary  := "NOT" unary | "-" unary | atom
    atom   := "(" query ")" | '"phrase"' | word
Matching is whole-token and case-insensitive (see skills.term_pattern).
Matching documents are ranked by how often the positive terms occur, with
log damping so repetition has diminishing returns.
"""
from __future__ import annotations

import math
import re
from dataclasses import dataclass

from .skills import SkillTaxonomy, count_term, default_taxonomy

_TOKEN = re.compile(r'\s*(\(|\)|"[^"]*"|[^\s()"]+)')


class QueryError(ValueError):
    pass


@dataclass
class Term:
    text: str


@dataclass
class Not:
    child: object


@dataclass
class And:
    children: list


@dataclass
class Or:
    children: list


def tokenize(q: str) -> list[str]:
    pos, out = 0, []
    q = q.strip()
    while pos < len(q):
        m = _TOKEN.match(q, pos)
        if not m:
            raise QueryError(f"cannot parse near: {q[pos:]!r}")
        out.append(m.group(1))
        pos = m.end()
    return out


def parse_query(q: str):
    tokens = tokenize(q)
    i = 0

    def peek():
        return tokens[i] if i < len(tokens) else None

    def take():
        nonlocal i
        i += 1
        return tokens[i - 1]

    def parse_or():
        kids = [parse_and()]
        while peek() and peek().upper() == "OR":
            take()
            kids.append(parse_and())
        return kids[0] if len(kids) == 1 else Or(kids)

    def parse_and():
        kids = [parse_unary()]
        while peek() and peek() != ")" and peek().upper() != "OR":
            if peek().upper() == "AND":
                take()
            kids.append(parse_unary())
        return kids[0] if len(kids) == 1 else And(kids)

    def parse_unary():
        t = peek()
        if t is None:
            raise QueryError("unexpected end of query")
        if t.upper() == "NOT" or t == "-":
            take()
            return Not(parse_unary())
        if t.startswith("-") and len(t) > 1:
            take()
            return Not(Term(t[1:].strip('"')))
        return parse_atom()

    def parse_atom():
        t = take()
        if t == "(":
            node = parse_or()
            if take_if(")") is None:
                raise QueryError("missing closing parenthesis")
            return node
        if t == ")" or t.upper() in {"AND", "OR"}:
            raise QueryError(f"unexpected {t!r}")
        return Term(t.strip('"'))

    def take_if(tok):
        if peek() == tok:
            return take()
        return None

    if not tokens:
        raise QueryError("empty query")
    tree = parse_or()
    if i != len(tokens):
        raise QueryError(f"unexpected {tokens[i]!r}")
    return tree


def _expand(term: str, taxonomy: SkillTaxonomy | None) -> list[str]:
    if taxonomy is None:
        return [term]
    canon = taxonomy.canonical(term)
    skill = taxonomy.get(canon) if canon else None
    return list(dict.fromkeys([term, *(skill.surface_forms if skill else ())]))


def evaluate(node, text: str, taxonomy: SkillTaxonomy | None = None) -> bool:
    if isinstance(node, Term):
        return any(count_term(text, f) for f in _expand(node.text, taxonomy))
    if isinstance(node, Not):
        return not evaluate(node.child, text, taxonomy)
    if isinstance(node, And):
        return all(evaluate(c, text, taxonomy) for c in node.children)
    if isinstance(node, Or):
        return any(evaluate(c, text, taxonomy) for c in node.children)
    raise TypeError(node)


def positive_terms(node, negated: bool = False) -> list[str]:
    if isinstance(node, Term):
        return [] if negated else [node.text]
    if isinstance(node, Not):
        return positive_terms(node.child, not negated)
    return [t for c in node.children for t in positive_terms(c, negated)]


@dataclass
class SearchHit:
    id: str
    score: float
    term_counts: dict[str, int]


def search(query: str, docs: dict[str, str], k: int = 10, expand_synonyms: bool = False) -> list[SearchHit]:
    """Return the top-k documents matching `query`, best first.

    `docs` maps a candidate id to its parsed resume text. With
    `expand_synonyms`, each term also matches its aliases in the curated
    taxonomy (some ATS offer this; plain Boolean search does not).
    """
    tree = parse_query(query)
    taxonomy = default_taxonomy() if expand_synonyms else None
    terms = list(dict.fromkeys(positive_terms(tree)))
    hits = []
    for doc_id, text in docs.items():
        if not evaluate(tree, text, taxonomy):
            continue
        counts = {t: sum(count_term(text, f) for f in _expand(t, taxonomy)) for t in terms}
        score = sum(1 + math.log(c) for c in counts.values() if c)
        hits.append(SearchHit(doc_id, round(score, 4), counts))
    hits.sort(key=lambda h: (-h.score, h.id))
    return hits[:k]
