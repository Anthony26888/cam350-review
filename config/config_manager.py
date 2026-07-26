import json
import os
from typing import Optional

from models.config import AppConfig


class ConfigManager:
    _instance: Optional["ConfigManager"] = None

    def __init__(self, config_path: Optional[str] = None) -> None:
        if config_path is None:
            self._config_path = os.path.join(
                os.path.dirname(os.path.abspath(__file__)), "config.json"
            )
        else:
            self._config_path = config_path
        self._config: AppConfig = self._load()

    @staticmethod
    def instance() -> "ConfigManager":
        if ConfigManager._instance is None:
            ConfigManager._instance = ConfigManager()
        return ConfigManager._instance

    def _load(self) -> AppConfig:
        if not os.path.exists(self._config_path):
            return AppConfig()
        try:
            with open(self._config_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            return AppConfig.from_dict(data)
        except (json.JSONDecodeError, IOError):
            return AppConfig()

    def save(self) -> None:
        data = self._config.to_dict()
        try:
            with open(self._config_path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=4)
        except IOError as e:
            raise RuntimeError(f"Failed to save config: {e}")

    @property
    def config(self) -> AppConfig:
        return self._config

    @config.setter
    def config(self, value: AppConfig) -> None:
        self._config = value
        self.save()

    def update(self, **kwargs) -> None:
        for key, value in kwargs.items():
            if hasattr(self._config, key):
                setattr(self._config, key, value)
        self.save()
