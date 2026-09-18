from abc import ABC, abstractmethod
from pathlib import Path

class BaseTool(ABC):
    @abstractmethod
    def convert(self, input_file: Path, output_file: Path, **kwargs) -> None:
        pass