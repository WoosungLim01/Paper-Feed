import json
import os
from dataclasses import dataclass, field
from typing import List

DATA_DIR = os.environ.get("DATA_DIR", "data")
SITE_DIR = os.environ.get("SITE_DIR", "site")
DAYS_BACK = int(os.environ.get("DAYS_BACK", "7"))
MAX_PER_SOURCE = int(os.environ.get("MAX_PER_SOURCE", "50"))
REQUEST_TIMEOUT = int(os.environ.get("REQUEST_TIMEOUT", "15"))


@dataclass
class SurveyConfig:
    topic_overview: str
    research_questions: List[str]
    question_context: str
    query_hints: List[str]
    timeline_from_year: int
    timeline_to_year: int
    min_relevance_score: float
    search_keywords: List[str] = field(default_factory=list)


def load_config(data_dir: str = DATA_DIR) -> SurveyConfig:
    config_path = os.path.join(data_dir, "survey_config.json")
    with open(config_path, "r", encoding="utf-8") as f:
        raw = json.load(f)
    return SurveyConfig(
        topic_overview=raw["topic_overview"],
        research_questions=raw.get("research_questions", []),
        question_context=raw.get("question_context", ""),
        query_hints=raw.get("query_hints", []),
        search_keywords=raw.get("search_keywords", raw.get("query_hints", [])),
        timeline_from_year=raw.get("timeline_from_year", 2020),
        timeline_to_year=raw.get("timeline_to_year", 2030),
        min_relevance_score=raw.get("min_relevance_score", 0.05),
    )
