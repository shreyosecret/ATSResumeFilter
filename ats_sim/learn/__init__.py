"""Learned (neural) section tagging that improves from confirmed resumes."""
from .labels import LABELS, SECTION_LABELS, label_lines, split_lines
from .tagger import LineTagger, parse_with_tagger, sections_from_labels

__all__ = ["LABELS", "SECTION_LABELS", "LineTagger", "label_lines", "parse_with_tagger",
           "sections_from_labels", "split_lines"]
