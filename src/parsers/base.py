"""Base parser interface for GC-MS data."""

from abc import ABC, abstractmethod
from pathlib import Path

from src.models import NaturalProfile


class BaseParser(ABC):
    """Abstract base class for GC-MS data parsers."""

    @abstractmethod
    def parse(self, file_path: Path) -> NaturalProfile:
        """Parse a GC-MS data file and return a NaturalProfile."""
        pass

    @abstractmethod
    def can_parse(self, file_path: Path) -> bool:
        """Check if this parser can handle the given file."""
        pass
