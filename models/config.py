from dataclasses import dataclass, field
from typing import Dict, Any


@dataclass
class Point:
    x: int = 0
    y: int = 0

    def to_dict(self) -> Dict[str, int]:
        return {"x": self.x, "y": self.y}

    @staticmethod
    def from_dict(data: Dict[str, int]) -> "Point":
        return Point(x=data.get("x", 0), y=data.get("y", 0))


@dataclass
class AppConfig:
    windowTitle: str = ""
    xTextbox: Point = field(default_factory=Point)
    yTextbox: Point = field(default_factory=Point)
    gotoButton: Point = field(default_factory=Point)
    delay: int = 150
    lastFile: str = ""
    lastReviewId: int = 0
    lastSessionFile: str = ""
    geometry: str = ""
    licenseKey: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "windowTitle": self.windowTitle,
            "xTextbox": self.xTextbox.to_dict(),
            "yTextbox": self.yTextbox.to_dict(),
            "gotoButton": self.gotoButton.to_dict(),
            "delay": self.delay,
            "lastFile": self.lastFile,
            "lastReviewId": self.lastReviewId,
            "lastSessionFile": self.lastSessionFile,
            "geometry": self.geometry,
            "licenseKey": self.licenseKey,
        }

    @staticmethod
    def from_dict(data: Dict[str, Any]) -> "AppConfig":
        return AppConfig(
            windowTitle=data.get("windowTitle", ""),
            xTextbox=Point.from_dict(data.get("xTextbox", {})),
            yTextbox=Point.from_dict(data.get("yTextbox", {})),
            gotoButton=Point.from_dict(data.get("gotoButton", {})),
            delay=data.get("delay", 150),
            lastFile=data.get("lastFile", ""),
            lastReviewId=data.get("lastReviewId", 0),
            lastSessionFile=data.get("lastSessionFile", ""),
            geometry=data.get("geometry", ""),
            licenseKey=data.get("licenseKey", ""),
        )
