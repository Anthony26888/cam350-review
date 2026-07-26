from dataclasses import dataclass, field
from typing import List, Optional


@dataclass
class PickPlaceComponent:
    designator: str = ""
    mpn: str = ""
    layer: str = ""
    x: float = 0.0
    y: float = 0.0
    rotation: float = 0.0
    row: int = 0


@dataclass
class PickPlaceData:
    headers: List[str] = field(default_factory=list)
    components: List[PickPlaceComponent] = field(default_factory=list)
    file_path: str = ""
    raw_data: List[dict] = field(default_factory=list)

    @property
    def count(self) -> int:
        return len(self.components)

    def get_component(self, index: int) -> Optional[PickPlaceComponent]:
        if 0 <= index < self.count:
            return self.components[index]
        return None
