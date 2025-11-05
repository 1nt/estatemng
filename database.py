import asyncio
from datetime import datetime
from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, UniqueConstraint, select
from sqlalchemy.orm import declarative_base
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

# Используем асинхронный движок для SQLite
DATABASE_URL = "sqlite+aiosqlite:///bot_database.db"
engine = create_async_engine(DATABASE_URL, echo=True, future=True)
Base = declarative_base()
SessionLocal = async_sessionmaker(
    bind=engine,
    autoflush=False,
    expire_on_commit=False,
    class_=AsyncSession,
)


# --- Модели таблиц ---

class User(Base):
    """Модель пользователя"""
    __tablename__ = 'users'
    id = Column(Integer, primary_key=True)
    telegram_id = Column(Integer, unique=True, nullable=False)
    username = Column(String, unique=True)
    full_name = Column(String)
    role = Column(String, default='resident')  # resident, specialist, manager


class Ticket(Base):
    """Модель заявки"""
    __tablename__ = 'tickets'
    id = Column(Integer, primary_key=True, autoincrement=True)
    resident_id = Column(Integer, ForeignKey('users.telegram_id'))
    specialist_id = Column(Integer, ForeignKey('users.telegram_id'), nullable=True)
    responsible_specialist_id = Column(Integer, ForeignKey('users.telegram_id'), nullable=True)
    
    location_queue = Column(String)
    location_entrance = Column(String)
    location_floor = Column(String)
    problem_type = Column(String)
    description = Column(String)
    photo_id = Column(String, nullable=True)
    
    # Поля для завершения заявки
    completion_comment = Column(String, nullable=True)
    completion_photo_id = Column(String, nullable=True)
    
    # Поля для отслеживания работы над заявкой
    taken_at = Column(DateTime, nullable=True)  # Дата когда взята в работу
    estimated_days = Column(Integer, nullable=True)  # Количество дней на выполнение
    completed_at = Column(DateTime, nullable=True)  # Дата выполнения
    
    status = Column(String, default='Новая')
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class SpecialistAssignment(Base):
    """Связка: тип проблемы -> username специалиста"""
    __tablename__ = 'specialist_assignments'
    id = Column(Integer, primary_key=True, autoincrement=True)
    problem_type = Column(String, nullable=False)
    specialist_username = Column(String, nullable=False)

    __table_args__ = (
        UniqueConstraint('problem_type', 'specialist_username', name='uq_problem_specialist'),
    )


# --- Функции для создания таблиц ---

async def create_db_and_tables():
    """Создает таблицы в базе данных при первом запуске"""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


# --- Функции для работы с данными ---

async def add_new_ticket(data: dict):
    """Добавляет новую заявку в базу данных"""
    async with SessionLocal() as session:
        new_ticket = Ticket(**data)
        session.add(new_ticket)
        await session.commit()
        await session.refresh(new_ticket)
        return new_ticket

async def get_ticket_by_id(ticket_id: int):
    """Получает заявку по её ID"""
    async with SessionLocal() as session:
        result = await session.execute(select(Ticket).where(Ticket.id == ticket_id))
        return result.scalars().first()


# --- Пользователи и специалисты ---

async def upsert_user(telegram_id: int, username: str | None, full_name: str | None, role: str | None = None):
    async with SessionLocal() as session:
        result = await session.execute(select(User).where(User.telegram_id == telegram_id))
        user = result.scalars().first()
        if user is None:
            user = User(telegram_id=telegram_id, username=username, full_name=full_name, role=role or 'resident')
            session.add(user)
        else:
            user.username = username or user.username
            user.full_name = full_name or user.full_name
            if role:
                user.role = role
        await session.commit()
        await session.refresh(user)
        return user

async def set_user_role_by_username(username: str, role: str):
    async with SessionLocal() as session:
        result = await session.execute(select(User).where(User.username == username))
        user = result.scalars().first()
        if user:
            user.role = role
            await session.commit()
            await session.refresh(user)
        return user

async def find_user_by_username(username: str):
    async with SessionLocal() as session:
        result = await session.execute(select(User).where(User.username == username))
        return result.scalars().first()

async def find_user_by_telegram_id(telegram_id: int):
    async with SessionLocal() as session:
        result = await session.execute(select(User).where(User.telegram_id == telegram_id))
        return result.scalars().first()

async def add_specialist_for_problem(problem_type: str, specialist_username: str):
    async with SessionLocal() as session:
        # ensure uniqueness
        result = await session.execute(
            select(SpecialistAssignment).where(
                (SpecialistAssignment.problem_type == problem_type) &
                (SpecialistAssignment.specialist_username == specialist_username)
            )
        )
        existing = result.scalars().first()
        if existing is None:
            assignment = SpecialistAssignment(problem_type=problem_type, specialist_username=specialist_username)
            session.add(assignment)
            await session.commit()
            return assignment
        return existing

async def list_specialists_for_problem(problem_type: str):
    async with SessionLocal() as session:
        result = await session.execute(select(SpecialistAssignment).where(SpecialistAssignment.problem_type == problem_type))
        return list(result.scalars().all())

async def get_open_tickets_for_specialist_username(specialist_username: str):
    # Найти типы проблем для специалиста и вернуть заявки в статусах "Новая" или "В работе"
    async with SessionLocal() as session:
        assignments_result = await session.execute(select(SpecialistAssignment).where(SpecialistAssignment.specialist_username == specialist_username))
        assignments = [a.problem_type for a in assignments_result.scalars().all()]
        if not assignments:
            return []
        result = await session.execute(select(Ticket).where(Ticket.problem_type.in_(assignments)))
        return list(result.scalars().all())

async def get_all_tickets():
    """Получить все заявки для модераторов"""
    async with SessionLocal() as session:
        result = await session.execute(select(Ticket).order_by(Ticket.created_at.desc()))
        return list(result.scalars().all())

async def update_ticket_status(ticket_id: int, status: str, responsible_specialist_id: int = None, completion_comment: str = None, completion_photo_id: str = None, estimated_days: int = None):
    """Обновить статус заявки и назначить ответственного специалиста"""
    async with SessionLocal() as session:
        result = await session.execute(select(Ticket).where(Ticket.id == ticket_id))
        ticket = result.scalars().first()
        if ticket:
            ticket.status = status
            if responsible_specialist_id:
                ticket.responsible_specialist_id = responsible_specialist_id
            if completion_comment:
                ticket.completion_comment = completion_comment
            if completion_photo_id:
                ticket.completion_photo_id = completion_photo_id
            if estimated_days is not None:
                ticket.estimated_days = estimated_days
            # Если статус "Взята в работу", сохраняем дату взятия
            if status == 'Взята в работу' and not ticket.taken_at:
                ticket.taken_at = datetime.utcnow()
            # Если статус "Выполнено", сохраняем дату выполнения
            if status == 'Выполнено' and not ticket.completed_at:
                ticket.completed_at = datetime.utcnow()
            ticket.updated_at = datetime.utcnow()
            await session.commit()
            await session.refresh(ticket)
        return ticket

# Для демонстрации создадим и асинхронно запустим создание таблиц
if __name__ == '__main__':
    asyncio.run(create_db_and_tables())