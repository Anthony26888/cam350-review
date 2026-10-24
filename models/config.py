from dataclasses import dataclass, field
from typing import Any, Dict, List


def _default_column_profiles() -> Dict[str, Dict[str, str]]:
    return {
        "Standard": {
            "designator": "Designator",
            "mpn": "MPN",
            "layer": "Layer",
            "x": "X",
            "y": "Y",
            "rotation": "Rotation",
        }
    }


@dataclass
class PrescreenConfig:
    enabled: bool = True
    rot_dev: float = 90.0
    rot_min_group: int = 2
    dup_tol: float = 0.05
    pad_median_tol: float = 2.0
    out_margin: float = 1.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "enabled": self.enabled,
            "rot_dev": self.rot_dev,
            "rot_min_group": self.rot_min_group,
            "dup_tol": self.dup_tol,
            "pad_median_tol": self.pad_median_tol,
            "out_margin": self.out_margin,
        }

    @staticmethod
    def from_dict(data: Dict[str, Any]) -> "PrescreenConfig":
        raw_rot_dev = float(data.get("rot_dev", 90.0))
        # Legacy default 45.0 -> upgrade (no UI exposes this knob)
        if raw_rot_dev == 45.0:
            raw_rot_dev = 90.0
        return PrescreenConfig(
            enabled=bool(data.get("enabled", True)),
            rot_dev=raw_rot_dev,
            rot_min_group=int(data.get("rot_min_group", 2)),
            dup_tol=float(data.get("dup_tol", 0.05)),
            pad_median_tol=float(data.get("pad_median_tol", 2.0)),
            out_margin=float(data.get("out_margin", 1.0)),
        )


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
    rotateButton: Point = field(default_factory=Point)
    delay: int = 150
    lastFile: str = ""
    lastReviewId: int = 0
    lastSessionFile: str = ""
    geometry: str = ""
    licenseKey: str = ""
    gerberGko: str = ""
    gerberGtp: str = ""
    gerberGbp: str = ""
    gerberGto: str = ""
    gerberGbo: str = ""
    gerberDrill: str = ""
    #: The folder the Gerber files were taken from.
    gerberFolder: str = ""
    #: The layers of the picture: the file of every layer, its name, its
    #: colour and its state.
    gerberLayers: List[Dict[str, Any]] = field(default_factory=list)
    theme: str = "light"
    language: str = "en"
    columnProfiles: Dict[str, Dict[str, str]] = field(default_factory=_default_column_profiles)
    lastColumnProfile: str = ""
    prescreen: PrescreenConfig = field(default_factory=PrescreenConfig)
    ecoMoveTol: float = 0.01
    ecoRotTol: float = 1.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "windowTitle": self.windowTitle,
            "xTextbox": self.xTextbox.to_dict(),
            "yTextbox": self.yTextbox.to_dict(),
            "gotoButton": self.gotoButton.to_dict(),
            "rotateButton": self.rotateButton.to_dict(),
            "delay": self.delay,
            "lastFile": self.lastFile,
            "lastReviewId": self.lastReviewId,
            "lastSessionFile": self.lastSessionFile,
            "geometry": self.geometry,
            "licenseKey": self.licenseKey,
            "gerberFolder": self.gerberFolder,
            "gerberLayers": self.gerberLayers,
            "theme": self.theme,
            "language": self.language,
            "columnProfiles": self.columnProfiles,
            "lastColumnProfile": self.lastColumnProfile,
            "prescreen": self.prescreen.to_dict(),
            "ecoMoveTol": self.ecoMoveTol,
            "ecoRotTol": self.ecoRotTol,
        }

    @staticmethod
    def from_dict(data: Dict[str, Any]) -> "AppConfig":
        return AppConfig(
            windowTitle=data.get("windowTitle", ""),
            xTextbox=Point.from_dict(data.get("xTextbox", {})),
            yTextbox=Point.from_dict(data.get("yTextbox", {})),
            gotoButton=Point.from_dict(data.get("gotoButton", {})),
            rotateButton=Point.from_dict(data.get("rotateButton", {})),
            delay=data.get("delay", 150),
            lastFile=data.get("lastFile", ""),
            lastReviewId=data.get("lastReviewId", 0),
            lastSessionFile=data.get("lastSessionFile", ""),
            geometry=data.get("geometry", ""),
            licenseKey=data.get("licenseKey", ""),
            gerberGko=data.get("gerberGko", ""),
            gerberGtp=data.get("gerberGtp", ""),
            gerberGbp=data.get("gerberGbp", ""),
            gerberGto=data.get("gerberGto", ""),
            gerberGbo=data.get("gerberGbo", ""),
    gerberDrill=data.get("gerberDrill", ""),
            gerberFolder=data.get("gerberFolder", ""),
            gerberLayers=list(data.get("gerberLayers", []) or []),
            theme=data.get("theme", "light"),
            language=data.get("language", "en"),
            columnProfiles=data.get("columnProfiles") or _default_column_profiles(),
            lastColumnProfile=data.get("lastColumnProfile", ""),
            prescreen=PrescreenConfig.from_dict(data.get("prescreen") or {}),
            ecoMoveTol=float(data.get("ecoMoveTol", 0.01)),
            ecoRotTol=float(data.get("ecoRotTol", 1.0)),
        )
