from datetime import UTC, datetime


def utcnow() -> datetime:
    """Retourne l'heure UTC en datetime naive pour le schema SQLAlchemy actuel."""
    return datetime.now(UTC).replace(tzinfo=None)
