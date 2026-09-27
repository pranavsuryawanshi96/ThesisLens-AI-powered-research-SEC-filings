import uuid

from sqlalchemy import Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.models.base import Base, TimestampMixin


class User(TimestampMixin, Base):
    """App-side profile for a Supabase Auth user.

    `id` equals `auth.users.id`. The foreign key to `auth.users` is added in the
    migration because the `auth` schema is owned by Supabase, not this metadata.
    """

    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    email: Mapped[str] = mapped_column(Text, unique=True)
    display_name: Mapped[str | None] = mapped_column(Text)

    threads: Mapped[list["ChatThread"]] = relationship(  # noqa: F821
        back_populates="user", cascade="all, delete-orphan", passive_deletes=True
    )
