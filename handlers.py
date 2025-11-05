from aiogram import Router, F, types
from aiogram.filters import Command
from aiogram.client.default import DefaultBotProperties
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import Message, CallbackQuery
import os

import keyboards as kb
import database as db

router = Router()

# --- Состояния для FSM (Finite State Machine) ---

class TicketState(StatesGroup):
    """Состояния для процесса создания заявки"""
    choosing_queue = State()
    choosing_entrance = State()
    choosing_floor = State()
    typing_floor = State()
    choosing_problem = State()
    typing_description = State()
    uploading_photo = State()

class CheckStatusState(StatesGroup):
    """Состояние для проверки статуса заявки"""
    waiting_for_id = State()


class ModAssignState(StatesGroup):
    choosing_problem_type = State()
    typing_username = State()

class StatusChangeState(StatesGroup):
    choosing_ticket = State()
    choosing_status = State()
    estimated_days = State()  # Для ввода количества дней при взятии в работу
    completion_comment = State()
    completion_photo = State()


# --- Обработчики основных команд ---

@router.message(Command("start"))
async def cmd_start(message: Message):
    # Регистрация/обновление пользователя
    full_name = message.from_user.full_name
    username = message.from_user.username
    user = await db.upsert_user(
        telegram_id=message.from_user.id,
        username=username,
        full_name=full_name,
    )

    # Если username есть в MODERATORS, назначим роль manager
    moderators = [u.strip().lstrip('@') for u in os.getenv('MODERATORS', '').split(',') if u.strip()]
    if username and username in moderators and user.role != 'manager':
        user = await db.upsert_user(
            telegram_id=message.from_user.id,
            username=username,
            full_name=full_name,
            role='manager',
        )

    # Роли: resident | specialist | manager
    role_to_menu = {
        'resident': kb.resident_menu,
        'specialist': kb.specialist_menu,
        'manager': kb.manager_menu,
    }

    await message.answer(
        (
            f"Здравствуйте! 👋\n\n"
            f"Ваша роль: <b>{user.role}</b>\n\n"
            f"Я чат-бот вашей Управляющей Компании. "
            f"Готов помочь вам с решением бытовых вопросов."
        ),
        parse_mode="HTML",
        reply_markup=role_to_menu.get(user.role, kb.resident_menu)
    )


# --- Команды модератора ---

async def _is_manager(user_id: int) -> bool:
    user = await db.upsert_user(telegram_id=user_id, username=None, full_name=None)
    return user.role == 'manager'


@router.message(Command("mod_add_specialist"))
async def mod_add_specialist(message: Message):
    if not await _is_manager(message.from_user.id):
        await message.answer("Команда доступна только модераторам.")
        return
    await message.answer("Выберите тип проблемы:", reply_markup=kb.mod_problem_type_kb)
    # Переводим в состояние ожидания выбора типа проблемы
    from aiogram.fsm.context import FSMContext
    # В aiogram3 нужно явное состояние через middleware, но используем простой подход:
    # попросим пользователя нажать кнопку и обработаем callback ниже.


@router.message(Command("mod_list_specialists"))
async def mod_list_specialists(message: Message):
    if not await _is_manager(message.from_user.id):
        await message.answer("Команда доступна только модераторам.")
        return

    args = (message.text or "").split(maxsplit=1)
    if len(args) < 2:
        await message.answer("Использование: /mod_list_specialists <тип_проблемы>")
        return
    problem_type = args[1].strip()
    specialists = await db.list_specialists_for_problem(problem_type)
    if not specialists:
        await message.answer("Специалисты не назначены.")
        return
    text = "\n".join([f"@{s.specialist_username}" for s in specialists])
    await message.answer(f"Специалисты для '{problem_type}':\n{text}")


@router.callback_query(F.data.startswith('mod_pt_'))
async def mod_choose_problem_type(callback: CallbackQuery, state: FSMContext):
    if not await _is_manager(callback.from_user.id):
        await callback.answer("Недостаточно прав", show_alert=True)
        return
    problem_type = callback.data.replace('mod_pt_', '', 1)
    await state.update_data(mod_problem_type=problem_type)
    await state.set_state(ModAssignState.typing_username)
    await callback.message.edit_text(
        f"Выбран тип: {problem_type}\nТеперь отправьте username специалиста в формате @username"
    )


@router.message(ModAssignState.typing_username)
async def mod_receive_username(message: Message, state: FSMContext):
    if not await _is_manager(message.from_user.id):
        await message.answer("Команда доступна только модераторам.")
        return
    username = (message.text or '').strip().lstrip('@')
    if not username:
        await message.answer("Укажите username в формате @username")
        return
    data = await state.get_data()
    problem_type = data.get('mod_problem_type')
    if not problem_type:
        await message.answer("Сначала выберите тип проблемы: /mod_add_specialist")
        await state.clear()
        return

    await db.add_specialist_for_problem(problem_type, username)
    specialist_user = await db.find_user_by_username(username)
    if specialist_user:
        await db.set_user_role_by_username(username, 'specialist')

    await message.answer(f"Добавлен специалист @{username} для типа: {problem_type}")
    await state.clear()


@router.message(Command("mod_set_role"))
async def mod_set_role(message: Message):
    if not await _is_manager(message.from_user.id):
        await message.answer("Команда доступна только модераторам.")
        return

    # Формат: /mod_set_role <username> <resident|specialist|manager>
    args = (message.text or "").split(maxsplit=2)
    if len(args) < 3:
        await message.answer("Использование: /mod_set_role <username> <resident|specialist|manager>")
        return
    username = args[1].strip().lstrip('@')
    role = args[2].strip()
    if role not in {"resident", "specialist", "manager"}:
        await message.answer("Недопустимая роль.")
        return
    user = await db.set_user_role_by_username(username, role)
    if user:
        await message.answer(f"Роль @{username} изменена на {role}.")
    else:
        await message.answer("Пользователь ещё не писал боту. Роль будет применена после первого сообщения.")

@router.message(F.text == "ℹ️ Справочная информация")
async def info_handler(message: Message):
    info_text = (
        "<b>Справочная информация:</b>\n\n"
        "📞 <b>Телефон УК:</b> +7 (XXX) XXX-XX-XX\n"
        "📧 <b>Почта УК:</b> support@uk-email.com\n\n"
        "<b>Аварийные службы:</b>\n"
        "🚨 <b>Общая аварийная:</b> 112\n"
        "💧 <b>Водоснабжение:</b> +7 (XXX) XXX-XX-XY\n"
        "⚡️ <b>Электроснабжение:</b> +7 (XXX) XXX-XX-XZ\n"
        "🛗 <b>Лифты:</b> +7 (XXX) XXX-XX-XW"
    )
    await message.answer(info_text, parse_mode="HTML")

@router.message(F.text == "🏠 Главное меню")
async def main_menu_handler(message: Message):
    # Регистрация/обновление пользователя
    full_name = message.from_user.full_name
    username = message.from_user.username
    user = await db.upsert_user(
        telegram_id=message.from_user.id,
        username=username,
        full_name=full_name,
    )

    # Если username есть в MODERATORS, назначим роль manager
    moderators = [u.strip().lstrip('@') for u in os.getenv('MODERATORS', '').split(',') if u.strip()]
    if username and username in moderators and user.role != 'manager':
        user = await db.upsert_user(
            telegram_id=message.from_user.id,
            username=username,
            full_name=full_name,
            role='manager',
        )

    # Роли: resident | specialist | manager
    role_to_menu = {
        'resident': kb.resident_menu,
        'specialist': kb.specialist_menu,
        'manager': kb.manager_menu,
    }

    await message.answer(
        (
            f"Здравствуйте! 👋\n\n"
            f"Ваша роль: <b>{user.role}</b>\n\n"
            f"Я чат-бот вашей Управляющей Компании. "
            f"Готов помочь вам с решением бытовых вопросов."
        ),
        parse_mode="HTML",
        reply_markup=role_to_menu.get(user.role, kb.resident_menu)
    )


# --- Меню действий для ролей ---

@router.message(F.text == "🧰 Мои заявки")
async def specialist_my_tickets(message: Message):
    user = await db.upsert_user(telegram_id=message.from_user.id, username=message.from_user.username, full_name=message.from_user.full_name)
    if user.role != 'specialist':
        await message.answer("Доступно только для специалистов.")
        return
    tickets = await db.get_open_tickets_for_specialist_username(user.username or '')
    if tickets:
        text_lines = ["Ваши заявки (только по вашим направлениям):"]
        for t in tickets[:10]:
            responsible = ""
            if t.responsible_specialist_id:
                responsible_user = await db.find_user_by_telegram_id(t.responsible_specialist_id)
                responsible_username = responsible_user.username if responsible_user else f"ID:{t.responsible_specialist_id}"
                responsible = f" (Ответственный: @{responsible_username})"
            text_lines.append(f"#{t.id} • {t.problem_type} • {t.status}{responsible}")
        await message.answer("\n".join(text_lines))
        # Отправим фото по заявкам, если они есть
        for t in tickets[:10]:
            if getattr(t, 'photo_id', None):
                caption = f"#{t.id} • {t.problem_type} • {t.status}"
                try:
                    await message.answer_photo(t.photo_id, caption=caption)
                except Exception:
                    pass
    else:
        await message.answer("Пока нет заявок по вашим направлениям.")

@router.message(F.text == "📋 Все заявки")
async def manager_all_tickets(message: Message):
    user = await db.upsert_user(telegram_id=message.from_user.id, username=message.from_user.username, full_name=message.from_user.full_name)
    if user.role != 'manager':
        await message.answer("Доступно только для модераторов.")
        return
    tickets = await db.get_all_tickets()
    if tickets:
        text_lines = ["Все заявки в системе:"]
        for t in tickets[:20]:  # Показываем последние 20 заявок
            responsible = ""
            if t.responsible_specialist_id:
                responsible_user = await db.find_user_by_telegram_id(t.responsible_specialist_id)
                responsible_username = responsible_user.username if responsible_user else f"ID:{t.responsible_specialist_id}"
                responsible = f" (Ответственный: @{responsible_username})"
            text_lines.append(f"#{t.id} • {t.problem_type} • {t.status} • {t.created_at.strftime('%d.%m %H:%M')}{responsible}")
        await message.answer("\n".join(text_lines))
        # Отправим фото по заявкам, если они есть
        for t in tickets[:20]:
            if getattr(t, 'photo_id', None):
                caption = f"#{t.id} • {t.problem_type} • {t.status} • {t.created_at.strftime('%d.%m %H:%M') }"
                try:
                    await message.answer_photo(t.photo_id, caption=caption)
                except Exception:
                    pass
    else:
        await message.answer("Заявок пока нет.")

@router.message(F.text == "🔄 Изменить статус заявки")
async def change_status_start(message: Message, state: FSMContext):
    user = await db.upsert_user(telegram_id=message.from_user.id, username=message.from_user.username, full_name=message.from_user.full_name)
    if user.role != 'specialist':
        await message.answer("Доступно только для специалистов.")
        return
    
    tickets = await db.get_open_tickets_for_specialist_username(user.username or '')
    if not tickets:
        await message.answer("У вас нет заявок для изменения статуса.")
        return
    
    # Создаем клавиатуру с заявками
    from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
    keyboard_buttons = []
    for t in tickets[:10]:  # Показываем первые 10 заявок
        keyboard_buttons.append([InlineKeyboardButton(
            text=f"#{t.id} • {t.problem_type} • {t.status}",
            callback_data=f"ticket_{t.id}"
        )])
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=keyboard_buttons)
    await message.answer("Выберите заявку для изменения статуса:", reply_markup=keyboard)
    await state.set_state(StatusChangeState.choosing_ticket)

@router.callback_query(F.data.startswith('ticket_'), StatusChangeState.choosing_ticket)
async def ticket_selected(callback: CallbackQuery, state: FSMContext):
    ticket_id = int(callback.data.split('_')[1])
    await state.update_data(selected_ticket_id=ticket_id)
    await state.set_state(StatusChangeState.choosing_status)
    
    ticket = await db.get_ticket_by_id(ticket_id)
    if ticket:
        await callback.message.edit_text(
            f"Заявка #{ticket.id} выбрана.\n"
            f"Тип: {ticket.problem_type}\n"
            f"Текущий статус: {ticket.status}\n\n"
            f"Выберите новый статус:",
            reply_markup=kb.status_change_kb
        )
        # Покажем фото проблемы, если есть
        if getattr(ticket, 'photo_id', None):
            try:
                await callback.message.answer_photo(ticket.photo_id, caption="Фото проблемы")
            except Exception:
                pass
    else:
        await callback.message.edit_text("Заявка не найдена.")
        await state.clear()

@router.callback_query(F.data.startswith('status_'), StatusChangeState.choosing_status)
async def status_changed(callback: CallbackQuery, state: FSMContext):
    user = await db.upsert_user(telegram_id=callback.from_user.id, username=callback.from_user.username, full_name=callback.from_user.full_name)
    if user.role != 'specialist':
        await callback.answer("Недостаточно прав", show_alert=True)
        return
    
    data = await state.get_data()
    ticket_id = data.get('selected_ticket_id')
    if not ticket_id:
        await callback.message.edit_text("Ошибка: заявка не выбрана.")
        await state.clear()
        return
    
    status_map = {
        'status_in_progress': 'Взята в работу',
        'status_completed': 'Выполнено',
        'status_not_found': 'Проблема не выявлена'
    }
    
    new_status = status_map.get(callback.data)
    if not new_status:
        await callback.answer("Неверный статус", show_alert=True)
        return
    
    # Если статус "Взята в работу", запрашиваем количество дней
    if new_status == 'Взята в работу':
        await state.update_data(new_status=new_status)
        await state.set_state(StatusChangeState.estimated_days)
        await callback.message.edit_text(
            f"Заявка #{ticket_id} будет взята в работу.\n\n"
            f"Введите количество дней на выполнение (или 0, если неизвестно):"
        )
    # Если статус "Выполнено", запрашиваем комментарий и фото
    elif new_status == 'Выполнено':
        await state.update_data(new_status=new_status)
        await state.set_state(StatusChangeState.completion_comment)
        await callback.message.edit_text(
            f"Заявка #{ticket_id} будет помечена как выполненная.\n\n"
            f"Добавьте комментарий о выполненной работе (или отправьте 'Пропустить'):"
        )
    else:
        # Для других статусов обновляем сразу
        updated_ticket = await db.update_ticket_status(ticket_id, new_status, callback.from_user.id)
        
        if updated_ticket:
            await callback.message.edit_text(
                f"✅ Статус заявки #{ticket_id} изменен на: {new_status}\n"
                f"Ответственный специалист: {callback.from_user.username or callback.from_user.full_name}"
            )
        else:
            await callback.message.edit_text("Ошибка при обновлении статуса.")
        
        await state.clear()

@router.message(StatusChangeState.estimated_days)
async def estimated_days_received(message: Message, state: FSMContext):
    """Обработчик ввода количества дней на выполнение"""
    data = await state.get_data()
    ticket_id = data.get('selected_ticket_id')
    new_status = data.get('new_status')
    
    if not message.text or not message.text.isdigit():
        await message.answer("Пожалуйста, введите число (количество дней, или 0 если неизвестно):")
        return
    
    estimated_days = int(message.text)
    if estimated_days < 0:
        await message.answer("Количество дней не может быть отрицательным. Введите число (или 0):")
        return
    
    # Обновляем заявку со статусом и количеством дней
    updated_ticket = await db.update_ticket_status(
        ticket_id, 
        new_status, 
        message.from_user.id,
        estimated_days=estimated_days
    )
    
    if updated_ticket:
        days_text = f"{estimated_days} дней" if estimated_days > 0 else "неизвестно"
        await message.answer(
            f"✅ Заявка #{ticket_id} взята в работу!\n"
            f"Срок выполнения: {days_text}\n"
            f"Ответственный специалист: @{message.from_user.username or message.from_user.full_name}"
        )
    else:
        await message.answer("Ошибка при обновлении статуса заявки.")
    
    await state.clear()

@router.message(StatusChangeState.completion_comment)
async def completion_comment_received(message: Message, state: FSMContext):
    data = await state.get_data()
    ticket_id = data.get('selected_ticket_id')
    new_status = data.get('new_status')
    
    comment = message.text if message.text != 'Пропустить' else None
    await state.update_data(completion_comment=comment)
    await state.set_state(StatusChangeState.completion_photo)
    
    await message.answer(
        f"Комментарий сохранен.\n\n"
        f"Теперь прикрепите фото выполненной работы (или отправьте любое сообщение, чтобы пропустить):"
    )

@router.message(StatusChangeState.completion_photo)
async def completion_photo_received(message: Message, state: FSMContext):
    data = await state.get_data()
    ticket_id = data.get('selected_ticket_id')
    new_status = data.get('new_status')
    comment = data.get('completion_comment')
    
    photo_id = None
    if message.photo:
        photo_id = message.photo[-1].file_id
    
    # Обновляем заявку с комментарием и фото
    updated_ticket = await db.update_ticket_status(
        ticket_id, 
        new_status, 
        message.from_user.id, 
        comment, 
        photo_id
    )
    
    if updated_ticket:
        # Отправляем уведомление создателю заявки
        try:
            resident_user = await db.find_user_by_telegram_id(updated_ticket.resident_id)
            if resident_user:
                notification_text = (
                    f"🔔 <b>Заявка #{ticket_id} выполнена!</b>\n\n"
                    f"<b>Проблема:</b> {updated_ticket.problem_type}\n"
                    f"<b>Статус:</b> {new_status}\n"
                    f"<b>Ответственный:</b> @{message.from_user.username or message.from_user.full_name}\n"
                )
                
                if comment:
                    notification_text += f"\n<b>Комментарий специалиста:</b>\n{comment}"
                
                await message.bot.send_message(
                    chat_id=updated_ticket.resident_id,
                    text=notification_text,
                    parse_mode="HTML"
                )
                
                # Отправляем фото, если есть
                if photo_id:
                    await message.bot.send_photo(
                        chat_id=updated_ticket.resident_id,
                        photo=photo_id,
                        caption="Фото выполненной работы"
                    )
        except Exception as e:
            # Если не удалось отправить уведомление, продолжаем
            pass
        
        await message.answer(
            f"✅ Заявка #{ticket_id} успешно выполнена!\n"
            f"Создатель заявки получил уведомление."
        )
    else:
        await message.answer("Ошибка при обновлении заявки.")
    
    await state.clear()


@router.message(F.text == "➕ Назначить специалиста")
async def manager_assign_entry(message: Message, state: FSMContext):
    user = await db.upsert_user(telegram_id=message.from_user.id, username=message.from_user.username, full_name=message.from_user.full_name)
    if user.role != 'manager':
        await message.answer("Доступно только для модераторов.")
        return
    await message.answer("Выберите тип проблемы:", reply_markup=kb.mod_problem_type_kb)


# --- Логика проверки статуса заявки ---

@router.message(F.text == "🔍 Проверить статус заявки")
async def check_status_start(message: Message, state: FSMContext):
    await message.answer("Пожалуйста, введите номер вашей заявки:")
    await state.set_state(CheckStatusState.waiting_for_id)

@router.message(CheckStatusState.waiting_for_id)
async def process_ticket_id(message: Message, state: FSMContext):
    if not message.text.isdigit():
        await message.answer("Номер заявки должен быть числом. Попробуйте ещё раз.")
        return

    ticket_id = int(message.text)
    ticket = await db.get_ticket_by_id(ticket_id)

    if ticket:
        # Получаем информацию об ответственном специалисте
        responsible_info = ""
        if ticket.responsible_specialist_id:
            responsible_user = await db.find_user_by_telegram_id(ticket.responsible_specialist_id)
            if responsible_user:
                responsible_info = f"\n<b>Ответственный:</b> @{responsible_user.username}"
            else:
                responsible_info = f"\n<b>Ответственный:</b> ID:{ticket.responsible_specialist_id}"
        
        response = (
            f"<b>Заявка №{ticket.id}</b>\n\n"
            f"<b>Статус:</b> {ticket.status}\n"
            f"<b>Проблема:</b> {ticket.problem_type}\n"
            f"<b>Описание:</b> {ticket.description}\n"
            f"<b>Дата создания:</b> {ticket.created_at.strftime('%d.%m.%Y %H:%M')}"
            f"{responsible_info}"
        )
        
        # Добавляем информацию о взятии в работу, если есть
        if ticket.taken_at:
            response += f"\n<b>Дата взятия в работу:</b> {ticket.taken_at.strftime('%d.%m.%Y %H:%M')}"
            if ticket.estimated_days is not None:
                days_text = f"{ticket.estimated_days} дней" if ticket.estimated_days > 0 else "неизвестно"
                response += f"\n<b>Срок выполнения:</b> {days_text}"
        
        # Добавляем информацию о завершении, если заявка выполнена
        if ticket.status == 'Выполнено':
            if ticket.completed_at:
                response += f"\n<b>Дата выполнения:</b> {ticket.completed_at.strftime('%d.%m.%Y %H:%M')}"
            if ticket.completion_comment:
                response += f"\n\n<b>Комментарий специалиста:</b>\n{ticket.completion_comment}"
        
        await message.answer(response, parse_mode="HTML")
        
        # Показываем фото проблемы, если есть
        if ticket.photo_id:
            await message.answer_photo(ticket.photo_id, caption="Фото проблемы:")
        
        # Показываем фото выполненной работы, если есть
        if ticket.status == 'Выполнено' and ticket.completion_photo_id:
            await message.answer_photo(ticket.completion_photo_id, caption="Фото выполненной работы:")
    else:
        await message.answer("Заявка с таким номером не найдена.")
    
    await state.clear()


# --- Логика создания новой заявки (FSM) ---

@router.message(F.text == "✍️ Сообщить о проблеме")
async def create_ticket_start(message: Message, state: FSMContext):
    await state.set_state(TicketState.choosing_queue)
    await message.answer("Выберите вашу очередь (корпус):", reply_markup=kb.queue_kb)

@router.callback_query(TicketState.choosing_queue)
async def queue_chosen(callback: CallbackQuery, state: FSMContext):
    await state.update_data(queue=callback.data.split('_')[1])
    await state.set_state(TicketState.choosing_entrance)
    await callback.message.edit_text("Теперь введите номер вашего подъезда (только цифру):")

@router.message(TicketState.choosing_entrance)
async def entrance_chosen(message: Message, state: FSMContext):
    if not message.text.isdigit():
        await message.answer("Пожалуйста, введите только номер подъезда (цифрой).")
        return
    await state.update_data(entrance=message.text)
    await state.set_state(TicketState.choosing_floor)
    await message.answer("Где именно проблема?", reply_markup=kb.floor_kb)

@router.callback_query(F.data.startswith('floor_'), TicketState.choosing_floor)
async def floor_chosen(callback: CallbackQuery, state: FSMContext):
    if callback.data == 'floor_common':
        await state.update_data(floor='Общедомовое')
        await state.set_state(TicketState.choosing_problem)
        await callback.message.edit_text("Выберите тип проблемы:", reply_markup=kb.problem_type_kb)
    else:
        await state.set_state(TicketState.typing_floor)
        await callback.message.edit_text("Введите номер этажа:")

@router.message(TicketState.typing_floor)
async def floor_typed(message: Message, state: FSMContext):
    if not message.text.isdigit():
        await message.answer("Пожалуйста, введите только номер этажа (цифрой).")
        return
    await state.update_data(floor=message.text)
    await state.set_state(TicketState.choosing_problem)
    await message.answer("Выберите тип проблемы:", reply_markup=kb.problem_type_kb)

@router.callback_query(F.data.startswith('problem_'), TicketState.choosing_problem)
async def problem_chosen(callback: CallbackQuery, state: FSMContext):
    problem_text_map = {
        'problem_light': 'Перегорела лампочка',
        'problem_water': 'Проблема с водой',
        'problem_elevator': 'Не работает лифт',
    }
    
    if callback.data == 'problem_other':
        await state.update_data(problem_type='Другое')
        await state.set_state(TicketState.typing_description)
        await callback.message.edit_text("Опишите проблему своими словами:")
    else:
        problem_text = problem_text_map.get(callback.data, 'Неизвестная проблема')
        await state.update_data(problem_type=problem_text, description=problem_text)
        await state.set_state(TicketState.uploading_photo)
        await callback.message.edit_text("Прикрепите фотографию проблемы или нажмите 'Пропустить'.")

@router.message(TicketState.typing_description)
async def description_typed(message: Message, state: FSMContext):
    await state.update_data(description=message.text)
    await state.set_state(TicketState.uploading_photo)
    await message.answer("Отлично. Теперь прикрепите фотографию проблемы или отправьте любое сообщение, чтобы пропустить этот шаг.")

@router.message(TicketState.uploading_photo)
async def photo_uploaded(message: Message, state: FSMContext):
    if message.photo:
        await state.update_data(photo_id=message.photo[-1].file_id)
    else:
        await state.update_data(photo_id=None)

    # --- Сбор всех данных и создание заявки ---
    data = await state.get_data()
    
    # TODO: Проверка на дубликаты перед созданием
    
    ticket_data_for_db = {
        'resident_id': message.from_user.id,
        'location_queue': data.get('queue'),
        'location_entrance': data.get('entrance'),
        'location_floor': data.get('floor'),
        'problem_type': data.get('problem_type'),
        'description': data.get('description'),
        'photo_id': data.get('photo_id')
    }
    
    new_ticket = await db.add_new_ticket(ticket_data_for_db)

    # Оповещение специалистов соответствующего типа
    specialists = await db.list_specialists_for_problem(new_ticket.problem_type)
    if specialists:
        mentions = ", ".join([f"@{s.specialist_username}" for s in specialists])
        await message.answer(
            f"🔔 Новый тикет #{new_ticket.id} ({new_ticket.problem_type}). Специалисты: {mentions}"
        )
        # Пытаемся отправить личные уведомления специалистам, которые уже взаимодействовали с ботом
        for s in specialists:
            specialist_user = await db.find_user_by_username(s.specialist_username)
            if specialist_user and specialist_user.telegram_id:
                try:
                    caption = (
                        f"🔔 Вам назначен новый тикет #{new_ticket.id}\n"
                        f"Тип: {new_ticket.problem_type}\n"
                        f"Описание: {new_ticket.description}"
                    )
                    if getattr(new_ticket, 'photo_id', None):
                        await message.bot.send_photo(
                            chat_id=specialist_user.telegram_id,
                            photo=new_ticket.photo_id,
                            caption=caption
                        )
                    else:
                        await message.bot.send_message(
                            chat_id=specialist_user.telegram_id,
                            text=caption
                        )
                except Exception:
                    pass
    
    await message.answer(
        f"✅ Ваша заявка принята! \n\n"
        f"Номер вашей заявки: <b>{new_ticket.id}</b>\n\n"
        "Вы можете отследить её статус в главном меню.",
        parse_mode="HTML",
        reply_markup=kb.main_menu
    )
    
    await state.clear()