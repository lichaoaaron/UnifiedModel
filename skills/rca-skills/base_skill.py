"""Base class for all MModel Skills."""
from abc import ABC, abstractmethod
from app.models.context import DiagnosisContext
from app.models.diagnosis import SkillResult


class BaseSkill(ABC):
    skill_name: str = ""
    title: str = ""

    @abstractmethod
    def run(self, ctx: DiagnosisContext) -> SkillResult:
        ...
