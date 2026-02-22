from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from wxcode_adm.config import settings

engine = create_async_engine(
    str(settings.DATABASE_URL),  # pydantic v2 Url object must be converted to str
    echo=settings.DEBUG,
    pool_pre_ping=True,  # verify connections before use (prevents cryptic errors after DB restart)
    pool_size=10,
    max_overflow=20,
)

async_session_maker = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,  # MANDATORY for async: prevents MissingGreenlet on attribute access after commit
)
