from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardMarkup, KeyboardButton

# --- Главное меню (жители) ---
resident_menu = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="ℹ️ Справочная информация")],
        [KeyboardButton(text="✍️ Сообщить о проблеме")],
        [KeyboardButton(text="🔍 Проверить статус заявки")]
    ],
    resize_keyboard=True
)

# --- Меню специалиста ---
specialist_menu = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="🧰 Мои заявки")],
        [KeyboardButton(text="🔄 Изменить статус заявки")],
        [KeyboardButton(text="🔍 Проверить статус заявки")],
        [KeyboardButton(text="ℹ️ Справочная информация")]
    ],
    resize_keyboard=True
)

# --- Меню модератора ---
manager_menu = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="➕ Назначить специалиста")],
        [KeyboardButton(text="📋 Все заявки")],
        [KeyboardButton(text="✍️ Сообщить о проблеме")],
        [KeyboardButton(text="🔍 Проверить статус заявки")],
        [KeyboardButton(text="ℹ️ Справочная информация")]
    ],
    resize_keyboard=True
)

# --- Клавиатуры для создания заявки ---
queue_kb = InlineKeyboardMarkup(inline_keyboard=[
    [InlineKeyboardButton(text="1-я Очередь", callback_data="queue_1")],
    [InlineKeyboardButton(text="2-я Очередь", callback_data="queue_2")]
])

floor_kb = InlineKeyboardMarkup(inline_keyboard=[
    [InlineKeyboardButton(text="Общедомовое имущество", callback_data="floor_common")],
    [InlineKeyboardButton(text="Указать этаж", callback_data="floor_specify")]
])

problem_type_kb = InlineKeyboardMarkup(inline_keyboard=[
    [InlineKeyboardButton(text="Перегорела лампочка", callback_data="problem_light")],
    [InlineKeyboardButton(text="Проблема с водой", callback_data="problem_water")],
    [InlineKeyboardButton(text="Не работает лифт", callback_data="problem_elevator")],
    [InlineKeyboardButton(text="Другое (описать)", callback_data="problem_other")]
])

# --- Клавиатура для модератора: выбор типа проблемы ---
mod_problem_type_kb = InlineKeyboardMarkup(inline_keyboard=[
    [InlineKeyboardButton(text="Перегорела лампочка", callback_data="mod_pt_Перегорела лампочка")],
    [InlineKeyboardButton(text="Проблема с водой", callback_data="mod_pt_Проблема с водой")],
    [InlineKeyboardButton(text="Не работает лифт", callback_data="mod_pt_Не работает лифт")],
    [InlineKeyboardButton(text="Другое", callback_data="mod_pt_Другое")]
])

# --- Клавиатура для смены статуса заявки ---
status_change_kb = InlineKeyboardMarkup(inline_keyboard=[
    [InlineKeyboardButton(text="Взята в работу", callback_data="status_in_progress")],
    [InlineKeyboardButton(text="Выполнено", callback_data="status_completed")],
    [InlineKeyboardButton(text="Проблема не выявлена", callback_data="status_not_found")]
])

# --- Главное меню (общее) ---
main_menu = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="🏠 Главное меню")]
    ],
    resize_keyboard=True
)

# --- Инлайн-кнопки пропуска шагов ---
skip_ticket_photo_kb = InlineKeyboardMarkup(inline_keyboard=[
    [InlineKeyboardButton(text="Пропустить", callback_data="skip_ticket_photo")]
])

skip_comment_kb = InlineKeyboardMarkup(inline_keyboard=[
    [InlineKeyboardButton(text="Пропустить", callback_data="skip_comment")]
])

skip_completion_photo_kb = InlineKeyboardMarkup(inline_keyboard=[
    [InlineKeyboardButton(text="Пропустить", callback_data="skip_completion_photo")]
])