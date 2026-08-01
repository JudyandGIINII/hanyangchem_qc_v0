"""SQLAlchemy persistence foundation for P2; the pure domain never imports this package."""

from hyc_data.models import Base

__all__ = ["Base"]
