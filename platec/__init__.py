"""
platec — núcleo analítico de la Plataforma Económica Inteligente.

Submódulos:
    data  : acceso a la base SQLite como objetos pandas + remuestreo a frecuencia común.
    stats : transformaciones estadísticas estándar (variaciones, medias móviles,
            detección de outliers, deflactación a términos reales).
"""
from . import data, stats  # noqa: F401

__all__ = ["data", "stats"]
