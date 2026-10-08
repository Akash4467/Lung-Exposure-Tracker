from lung.engine.config import EngineConfig


def cigarettes(avg_pm25_24h: float, cfg: EngineConfig) -> float:
    """Cigarette equivalent of a 24 h average. A communication aid, not a health claim."""
    return avg_pm25_24h / cfg.cigarette_ugm3
