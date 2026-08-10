from dataclasses import dataclass, field


@dataclass
class PcbInfo:
    board_width: float = 0.0
    board_height: float = 0.0
    working_area_width: float = 0.0
    position_working: float = 0.0
    x_boc1: float = 0.0
    y_boc1: float = 0.0
    x_boc2: float = 0.0
    y_boc2: float = 0.0
    x_boc3: float = 0.0
    y_boc3: float = 0.0
    thickness: float = 1.6

    def has_data(self) -> bool:
        return bool(
            self.board_width
            or self.board_height
            or self.working_area_width
            or self.position_working
            or self.x_boc1 or self.y_boc1
            or self.x_boc2 or self.y_boc2
            or self.x_boc3 or self.y_boc3
            or self.thickness
        )

    def to_row(self) -> list:
        return [
            self.board_width,
            self.board_height,
            self.working_area_width,
            self.position_working,
            self.x_boc1,
            self.y_boc1,
            self.x_boc2,
            self.y_boc2,
            self.x_boc3,
            self.y_boc3,
            self.thickness,
        ]

    def to_dict(self) -> dict:
        return {
            "board_width": self.board_width,
            "board_height": self.board_height,
            "working_area_width": self.working_area_width,
            "position_working": self.position_working,
            "x_boc1": self.x_boc1,
            "y_boc1": self.y_boc1,
            "x_boc2": self.x_boc2,
            "y_boc2": self.y_boc2,
            "x_boc3": self.x_boc3,
            "y_boc3": self.y_boc3,
            "thickness": self.thickness,
        }

    @staticmethod
    def from_dict(data: dict) -> "PcbInfo":
        return PcbInfo(
            board_width=data.get("board_width", 0.0),
            board_height=data.get("board_height", 0.0),
            working_area_width=data.get("working_area_width", 0.0),
            position_working=data.get("position_working", 0.0),
            x_boc1=data.get("x_boc1", 0.0),
            y_boc1=data.get("y_boc1", 0.0),
            x_boc2=data.get("x_boc2", 0.0),
            y_boc2=data.get("y_boc2", 0.0),
            x_boc3=data.get("x_boc3", 0.0),
            y_boc3=data.get("y_boc3", 0.0),
            thickness=data.get("thickness", 1.6),
        )
