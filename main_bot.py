import telebot
from telebot import types
import config
import database
import connect
import threading
import matplotlib.pyplot as plt
from io import BytesIO
from datetime import datetime
import os
import subprocess
import platform
from neyro import sozdanie
import time

def play_media_fullscreen(path: str):
    """Кросс-платформенный запуск media в максимизированном/fullscreen режиме."""
    if platform.system() == "Windows":
        # открываем в максимально развернутом окне
        subprocess.Popen(f'cmd /c start "" /MAX "{path}"', shell=True)
    else:
        # Linux/RPi
        subprocess.Popen(["omxplayer", "-b", "--loop", path])

# Инициализация базы данных
database.init_db()
connect.init_ser()
bot = telebot.TeleBot(config.BOT_TOKEN)
user_states: dict[int, dict] = {}

MENU_MAIN = [
    "Конфигурация оборудования",
    "Получение показаний",
    "Отправка управляющего сигнала",
    "Сценарии",
    "Мультимедиа",
    "Генерация изображения",
    "Администрация"
]


CONF_MENU = [
    "Добавить устройство",
    "Редактировать устройство",
    "Удалить устройство",
    "Вернуться в главное меню"
]
ADD_MENU = [
    "Датчик",
    "Исполнительное",
    "Вернуться в главное меню"
]

# Подсказки для полей
SENSOR_PROMPTS = {
    'name': 'Введите name (строка): название датчика',
    'description': 'Введите description (строка): описание датчика',
    'channel': 'Введите channel (число): канал связи',
    'pin': 'Введите pin (число): номер пина',
    'interval_sec': 'Введите interval_sec (число): период опроса в секундах'
}
ACTOR_PROMPTS = {
    'name': 'Введите name (строка): название актора',
    'description': 'Введите description (строка): описание актора',
    'channel': 'Введите channel (число): канал связи',
    'pin': 'Введите pin (число): номер пина',
    'interval_sec': 'Введите interval_sec (число) или "-" для ручного режима: период срабатывания в секундах',
    'value': 'Введите value (число 0–255): интенсивность работы',
    'duration': 'Введите duration (число сек) или "-" для без возврата'
}
# Поля, требующие int()
NUMERIC_FIELDS = {'channel','pin','min_val','max_val','interval_sec','value','duration'}

# Функция-заглушка отправки сигнала
def send_signal(channel: int, pin: int, value: int) -> None:
    """Заглушка отправки управляющего сигнала"""
    print(connect.act(channel,pin,value))

# Фоновые опросы сенсоров
def poll_sensor(sensor_id: int):
    sensor = database.get_sensor_by_id(sensor_id)
    if not sensor or sensor['interval_sec'] <= 0:
        return

    # опрос датчика
    # опрос датчика
    # опрос и получение значения
    value = database.get_data(sensor['channel'], sensor['pin'])
    # сразу проверяем скрипты
    check_scripts_for_sensor(sensor_id, value)
    # планируем следующий опрос
    t = threading.Timer(
        sensor['interval_sec'],
        lambda: threading.Thread(target=poll_sensor, args=(sensor_id,), daemon=True).start()
    )
    t.daemon = True
    t.start()

def check_scripts_for_sensor(sensor_id: int, value: float):
    for s in database.list_scripts_by_sensor(sensor_id):
        value = value
        cond = (value >= s['threshold']) if s['type_of_script'] else (value <= s['threshold'])
        sig = s['actor_value'] if cond else 0
        # получаем канал/пин актора
        actor = database.get_actor_by_id(s['actor_id'])
        if actor:
            send_signal(actor['channel'], actor['pin'], sig)

def monitor_script(script_id: int):
    s = database.get_script_by_id(script_id)
    if not s:
        return

    # проверяем порог
    last = database.get_last_sensor_reading(s['sensor_id'])
    val = last['value'] if last else None

    if val is not None and val >= s['threshold']:
        # включаем актор
        send_signal(s['channel'], s['pin'], s['actor_value'])
        # планируем выключение через duration минут
        t_off = threading.Timer(
            s['actor_duration'] * 60,
            lambda: send_signal(s['channel'], s['pin'], 0)
        )
        t_off.daemon = True
        t_off.start()
    # планируем следующий «чек» через небольшую задержку (например, 5 секунд)
    t_next = threading.Timer(
        5,
        lambda: monitor_script(script_id)
    )
    t_next.daemon = True
    t_next.start()


def poll_actor(actor_id: int):
    actor = database.get_actor_by_id(actor_id)
    if not actor or actor['interval_sec'] <= 0:
        return

    # 1) включаем
    send_signal(actor['channel'], actor['pin'], actor['value'])

    dur = actor['duration']
    ival = actor['interval_sec']

    if dur and dur > 0:
        # функция «выключения + планирование следующего цикла»
        def off_and_schedule():
            send_signal(actor['channel'], actor['pin'], 0)
            # теперь ждём interval_sec и запускаем новый цикл
            t_next = threading.Timer(
                ival,
                lambda: threading.Thread(target=poll_actor, args=(actor_id,), daemon=True).start()
            )
            t_next.daemon = True
            t_next.start()

        t_off = threading.Timer(dur, off_and_schedule)
        t_off.daemon = True
        t_off.start()

    else:
        # если duration=0 — простая рутинная отправка value по интервалу
        t_cycle = threading.Timer(
            ival,
            lambda: threading.Thread(target=poll_actor, args=(actor_id,), daemon=True).start()
        )
        t_cycle.daemon = True
        t_cycle.start()





# Запустить опросы при старте
def start_polling_all():
    for s in database.list_sensors():
        if s['interval_sec'] and s['interval_sec'] > 0:
            threading.Thread(target=poll_sensor, args=(s["id"],), daemon=True).start()
        time.sleep(15)
    for a in database.list_actors():
        if a['interval_sec'] and a['interval_sec'] > 0:
            threading.Thread(target=poll_actor, args=(a['id'],), daemon=True).start()
        time.sleep(15)

# Обработчики команд и сообщений
@bot.message_handler(commands=['start'])
def start_handler(message):
    chat_id = message.chat.id
    user_states.pop(chat_id, None)
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    for btn in MENU_MAIN:
        markup.add(types.KeyboardButton(btn))
    bot.send_message(chat_id, "Добро пожаловать в Smart Home Bot! Выберите действие:", reply_markup=markup)

@bot.message_handler(func=lambda m: True)
def text_handler(message):
    chat_id = message.chat.id
    text = message.text

    # проверка прав администратора
    username = message.from_user.username
    if not username or f"@{username}" not in database.list_admins():
        bot.send_message(chat_id,
            'Вы не являетесь администратором. Для добавления в реестр обратитесь к администратору'
        )
        return

    # возврат в главное меню
    if text == "Вернуться в главное меню":
        return start_handler(message)

    # если в процессе диалога
    if chat_id in user_states:
        return process_state(message)

    # основное меню
    if text == "Конфигурация оборудования":
        markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
        for btn in CONF_MENU:
            markup.add(types.KeyboardButton(btn))
        bot.send_message(chat_id, "Выберите действие по конфигурации:", reply_markup=markup)
    
    elif text == "Редактировать устройство":
        markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
        for btn in ADD_MENU:
            markup.add(types.KeyboardButton(btn))
        user_states[chat_id] = {'action': 'edit', 'type': None, 'step': 0}
        bot.send_message(chat_id, "Что вы хотите редактировать?", reply_markup=markup)

    elif text == "Удалить устройство":
        markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
        for btn in ADD_MENU:
            markup.add(types.KeyboardButton(btn))
        user_states[chat_id] = {'action': 'delete', 'type': None, 'step': 0}
        bot.send_message(chat_id, "Что вы хотите удалить?", reply_markup=markup)

    elif text == "Добавить устройство":
        markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
        for btn in ADD_MENU:
            markup.add(types.KeyboardButton(btn))
        user_states[chat_id] = {'action': 'add', 'type': None, 'step': 0, 'data': {}}
        bot.send_message(chat_id, "Что вы хотите добавить?", reply_markup=markup)

    elif text == "Получение показаний":
        sensors = database.list_sensors()
        markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
        for s in sensors:
            markup.add(types.KeyboardButton(f"{s['id']}-{s['name']}"))
        user_states[chat_id] = {'action': 'get_data', 'step': 0}
        bot.send_message(chat_id, "Выберите датчик:", reply_markup=markup)

    elif text == "Отправка управляющего сигнала":
        actors = database.list_actors()
        markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
        for a in actors:
            markup.add(types.KeyboardButton(f"{a['id']}-{a['name']}"))
        user_states[chat_id] = {'action': 'control', 'step': 0}
        bot.send_message(chat_id, "Выберите актор:", reply_markup=markup)

    elif text == "Сценарии":
        markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
        markup.add(types.KeyboardButton("Создать сценарий"))
        markup.add(types.KeyboardButton("Изменить сценарий"))
        markup.add(types.KeyboardButton("Удалить сценарий"))
        markup.add(types.KeyboardButton("Вернуться в главное меню"))
        user_states[chat_id] = {'action': 'script_menu', 'step': 0, 'data': {}}
        bot.send_message(chat_id, "Меню сценариев:", reply_markup=markup)


    elif text == "Мультимедиа":
        markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
        markup.add(types.KeyboardButton("Загрузить файл"))
        markup.add(types.KeyboardButton("Начало воспроизведения"))
        markup.add(types.KeyboardButton("Остановить воспроизведение"))
        markup.add(types.KeyboardButton("Вернуться в главное меню"))
        user_states[chat_id] = {'action': 'media', 'step': 0}
        bot.send_message(chat_id, "Меню мультимедиа:", reply_markup=markup)

    elif text == "Генерация изображения":
        user_states[chat_id] = {'action': 'generate_image', 'step': 0, 'data': {}}
        bot.send_message(chat_id, "Введите текстовый запрос для генерации изображения:")

    elif text == "Администрация":
        markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
        markup.add(types.KeyboardButton("Добавить администратора"))
        markup.add(types.KeyboardButton("Удалить администратора"))
        user_states[chat_id] = {'action': 'admin', 'step': 0}
        bot.send_message(chat_id, "Меню администратора:", reply_markup=markup)

    else:
        bot.send_message(chat_id, "Неизвестная команда. Используйте меню.")

# Обработка состояний

def process_state(message):
    chat_id = message.chat.id
    text = message.text
    state = user_states[chat_id]

    # — Генерация изображения —
    if state['action'] == 'generate_image':
        # step 0: получили промт
        if state['step'] == 0:
            state['data']['prompt'] = text
            state['step'] = 1
            bot.send_message(chat_id, "Введите имя файла для сохранения (без расширения):")
            return

        # step 1: получили имя файла — генерируем
        if state['step'] == 1:
            filename = text.strip()
            prompt = state['data']['prompt']
            try:
                sozdanie(prompt, filename)
                bot.send_message(chat_id, f"Изображение сгенерировано и сохранено как {filename}.png")
            except Exception as e:
                bot.send_message(chat_id, f"Ошибка генерации: {e}")
            user_states.pop(chat_id)
            return start_handler(message)

    # — меню сценариев: выбор действия —
    if state['action'] == 'script_menu':
        if state['step'] == 0:
            if text == "Создать сценарий":
                # перенаправляем в уже существующую логику создания
                state['action'] = 'script_add'
                state['step'] = 0
                bot.send_message(chat_id, "Введите уникальное имя сценария:")
            elif text == "Изменить сценарий":
                state['action'] = 'script_edit'
                state['step'] = 0
                # список сценариев
                scripts = database.list_scripts()
                markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
                for s in scripts:
                    markup.add(types.KeyboardButton(f"{s['id']}-{s['name']}"))
                markup.add(types.KeyboardButton("Вернуться в главное меню"))
                bot.send_message(chat_id, "Выберите сценарий для редактирования:", reply_markup=markup)
            elif text == "Удалить сценарий":
                state['action'] = 'script_delete'
                state['step'] = 0
                scripts = database.list_scripts()
                markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
                for s in scripts:
                    markup.add(types.KeyboardButton(f"{s['id']}-{s['name']}"))
                markup.add(types.KeyboardButton("Вернуться в главное меню"))
                bot.send_message(chat_id, "Выберите сценарий для удаления:", reply_markup=markup)
            else:  # Вернуться
                user_states.pop(chat_id)
                return start_handler(message)
            return

    # — создание сценария —
    if state['action'] == 'script_add':
        # step 0: имя
        if state['step'] == 0:
            state['data']['name'] = text.strip()
            state['step'] = 1
            # список датчиков
            sensors = database.list_sensors()
            markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
            for s in sensors:
                markup.add(types.KeyboardButton(f"{s['id']}-{s['name']}"))
            bot.send_message(chat_id, "Какой датчик будет триггером?", reply_markup=markup)
            return
        # step 1: датчик
        if state['step'] == 1:
            state['data']['sensor_id'] = int(text.split('-')[0])
            state['step'] = 2
            bot.send_message(chat_id, "Введите порог срабатывания (число):")
            return
        # step 2: threshold
        if state['step'] == 2:
            state['data']['threshold'] = float(text)
            state['step'] = 3
            # список акторов
            actors = database.list_actors()
            markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
            for a in actors:
                markup.add(types.KeyboardButton(f"{a['id']}-{a['name']}"))
            bot.send_message(chat_id, "Какой актор включать?", reply_markup=markup)
            return
        # step 3: актор
        if state['step'] == 3:
            state['data']['actor_id'] = int(text.split('-')[0])
            state['step'] = 4
            bot.send_message(chat_id, "Введите мощность актора (0–255):")
            return
        # step 4: actor_value
        if state['step'] == 4:
            state['data']['actor_value'] = int(text)
            state['step'] = 5
            bot.send_message(chat_id, "Введите тип сценария (True — срабатывает при ≥threshold; False — при ≤threshold):")
            return

        # step 5: type_of_script
        if state['step'] == 5:
            state['data']['type_of_script'] = True if text.lower() == 'true' else False
            script_id = database.add_script(state['data'])
            bot.send_message(chat_id, f"Сценарий «{state['data']['name']}» создан!")
            user_states.pop(chat_id)
            return start_handler(message)

    # — редактирование сценария —
    if state['action'] == 'script_edit':
        # шаг 0: выбрали сценарий
        if state['step'] == 0:
            state['script_id'] = int(text.split('-')[0])
            state['step'] = 1
            bot.send_message(chat_id, "Введите новое пороговое значение (threshold):")
            return
        # шаг 1: новый threshold
        if state['step'] == 1:
            new_thr = float(text)
            database.update_script(state['script_id'], 'threshold', new_thr)
            bot.send_message(chat_id, "Порог сценария обновлён")
            # перезапуск мониторинга (если нужно)
            state.clear()
            user_states.pop(chat_id)
            return start_handler(message)
    # — удаление сценария —
    if state['action'] == 'script_delete':
        # шаг 0: выбрали сценарий
        script_id = int(text.split('-')[0])
        database.delete_script(script_id)
        bot.send_message(chat_id, "Сценарий удалён")
        user_states.pop(chat_id)
        return start_handler(message)

    # — добавление устройства —
    if state['action'] == 'add':
        # выбор типа
        if state['type'] is None:
            if text == "Датчик":
                state.update({'type': 'sensor', 'fields': list(SENSOR_PROMPTS.keys()), 'step': 0, 'data': {}})
                bot.send_message(chat_id, SENSOR_PROMPTS['name'])
            elif text == "Исполнительное":
                state.update({'type': 'actor', 'fields': list(ACTOR_PROMPTS.keys()), 'step': 0, 'data': {}})
                bot.send_message(chat_id, ACTOR_PROMPTS['name'])
            else:
                bot.send_message(chat_id, "Выберите из меню.")
            return

        # ввод полей
        key = state['fields'][state['step']]
        if key in ['interval_sec', 'duration']:
            # и для duration тоже '-' → 0
            val = 0 if text.strip() == '-' else int(text)
        elif key in NUMERIC_FIELDS:
            val = int(text)
        else:
            val = text
        state['data'][key] = val
        state['step'] += 1

        if state['step'] < len(state['fields']):
            next_key = state['fields'][state['step']]
            prompt = (SENSOR_PROMPTS if state['type'] == 'sensor' else ACTOR_PROMPTS)[next_key]
            bot.send_message(chat_id, prompt)
        else:
            # сохранение
            if state['type'] == 'sensor':
                sid = database.add_sensor(state['data'])
                bot.send_message(chat_id, "Датчик успешно добавлен!")
                sensor = database.get_sensor_by_id(sid)
                if sensor['interval_sec'] > 0:
                    threading.Thread(target=poll_sensor, args=(sensor["id"],), daemon=True).start()
            else:
                aid = database.add_actor(state['data'])
                bot.send_message(chat_id, "Актор успешно добавлен!")
                actor = next(a for a in database.list_actors() if a['id'] == aid)
                if actor['interval_sec'] > 0:
                    threading.Thread(target=poll_actor, args=(actor['id'],), daemon=True).start()
            user_states.pop(chat_id)
        return #start_handler(message)
    
    # — Мультимедиа —
    if state['action'] == 'media':
        print(f"DEBUG: entered media FSM, step={state['step']}, state={state}")
        
        # шаг 0: выбор операции
        if state['step'] == 0:
            print("DEBUG: media step 0, user pressed:", text)
            if text == "Загрузить файл":
                state['step'] = 1
                state['media_action'] = 'upload'
                bot.send_message(chat_id, "Отправьте медиафайл:")
            elif text == "Начало воспроизведения":
                state['step'] = 2
                BASE_DIR = r"G:\Kodi\22052025v1Kvant\home\files"
                files = os.listdir(BASE_DIR)
                markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
                for fn in files:
                    markup.add(types.KeyboardButton(fn))
                markup.add(types.KeyboardButton("Вернуться в главное меню"))
                bot.send_message(chat_id, "Выберите файл для воспроизведения:", reply_markup=markup)
            
            elif text == "Остановить воспроизведение":
                if platform.system() == "Windows":
                    # убиваем стандартные UWP-приложения «Фото», «Фильмы и ТВ» и Windows Media Player
                    for proc in ("Photos.exe", "Video.UI.exe", "wmplayer.exe"):
                        subprocess.Popen(
                            ["taskkill", "/IM", proc, "/F"],
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                            shell=True
                        )
                else:
                    # глушим omxplayer, fbi, mplayer и vlc на RaspberryOS
                    for proc in ("omxplayer.bin", "fbi", "mplayer", "vlc"):
                        subprocess.Popen(["pkill", proc], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                bot.send_message(chat_id, "Воспроизведение остановлено")
                user_states.pop(chat_id)    
                return start_handler(message)
            
            return
    
        # шаг 1: ждём, что media_upload_handler скачает и запросит имя
        if state['step'] == 1:
            print("DEBUG: media step 1, waiting for file upload")
            return
    
        # шаг 2: пользователь выбрал файл из списка для воспроизведения
        if state['step'] == 2:
            print("DEBUG: media step 2, user chose file:", text)
            if text == "Вернуться в главное меню":
                user_states.pop(chat_id)
                return start_handler(message)
            path = rf"G:\Kodi\22052025v1Kvant\home\files\{text}"
            play_media_fullscreen(path)
            bot.send_message(chat_id, "Воспроизведение запущено")
            user_states.pop(chat_id)
            return start_handler(message)
    
        # шаг 3: пользователь вводит имя для последнего загруженного файла
        if state['step'] == 3:
            print("DEBUG: media step 3, saving uploaded data with filename:", text)
            filename = text.strip()
            dl = state.get('downloaded')
            if not dl:
                bot.send_message(chat_id, "Ошибка: нет загруженных данных.")
                user_states.pop(chat_id)
                return start_handler(message)
    
            BASE_DIR = r"G:\Kodi\22052025v1Kvant\home\files"
            os.makedirs(BASE_DIR, exist_ok=True)
            local_path = os.path.join(BASE_DIR, f"{filename}{dl['ext']}")
            try:
                with open(local_path, 'wb') as f:
                    f.write(dl['data'])
                print("DEBUG: file written successfully to", local_path)
                bot.send_message(chat_id, f"Файл сохранён: {local_path}")
            except Exception as e:
                print("ERROR: failed to write file:", e)
                bot.send_message(chat_id, "Ошибка при сохранении файла.")
                user_states.pop(chat_id)
                return start_handler(message)
    
            # сразу воспроизводим
            play_media_fullscreen(local_path)
            bot.send_message(chat_id, "Воспроизведение запущено")
    
            user_states.pop(chat_id)
            return start_handler(message)



    # — получение показаний —
    if state['action'] == 'get_data':
        if state['step'] == 0:
            state['sensor_id'] = int(text.split('-')[0])
            state['step'] = 1
            bot.send_message(chat_id, "За сколько минут? (число)")
            return
        # построение графика
        minutes = int(text)
        data = database.get_sensor_data(state['sensor_id'], minutes)
        if not data:
            bot.send_message(chat_id, "Нет данных за указанный период.")
        else:
            times = [datetime.strptime(r['timestamp'], "%Y-%m-%d %H:%M:%S") for r in data]
            vals = [r['value'] for r in data]
            n = len(times)
            if n > 1:
                # 4 равных отрезка → 5 точек
                idx = [int(i * (n-1) / 4) for i in range(5)]
            else:
                idx = list(range(n))
            tcks = [times[i] for i in idx]
            labs = [t.strftime('%H:%M') for t in tcks]
            plt.figure()
            plt.plot(times, vals)
            plt.xticks(tcks, labs)
            plt.xlabel('Время')
            plt.ylabel('Значение')
            plt.tight_layout()
            buf = BytesIO()
            plt.savefig(buf, format='png')
            buf.seek(0)
            plt.close()
            bot.send_photo(chat_id, buf)
        user_states.pop(chat_id)
        return start_handler(message)

    # — редактирование устройства —
    if state['action'] == 'edit':
        if state['type'] is None:
            if text == 'Датчик':
                state['type'] = 'sensor'
                items = database.list_sensors()
            else:
                state['type'] = 'actor'
                items = database.list_actors()
            markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
            for itm in items:
                markup.add(types.KeyboardButton(f"{itm['id']}-{itm['name']}"))
            bot.send_message(chat_id, "Выберите объект для редактирования:", reply_markup=markup)
            state['step'] = 0
            return
        if state['step'] == 0:
            state['id'] = int(text.split('-')[0])
            fields = list(SENSOR_PROMPTS.keys()) if state['type'] == 'sensor' else list(ACTOR_PROMPTS.keys())
            markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
            for idx, f in enumerate(fields, 1):
                markup.add(types.KeyboardButton(f"{idx}.{f}"))
            bot.send_message(chat_id, "Введите номер параметра для изменения:", reply_markup=markup)
            state['fields'] = fields
            state['step'] = 1
            return
        if state['step'] == 1:
            idx = int(text.split('.')[0]) - 1
            field = state['fields'][idx]
            state['field'] = field
            state['step'] = 2
            prompt = (SENSOR_PROMPTS if state['type'] == 'sensor' else ACTOR_PROMPTS)[field]
            bot.send_message(chat_id, prompt)
            return
        if state['step'] == 2:
            field = state['field']
            val = int(text) if field in NUMERIC_FIELDS else text
            if state['type'] == 'sensor':
                database.update_sensor(state['id'], state['field'], val)
                # перезапустить фоновый опрос сенсора с новыми параметрами
                sensor = database.get_sensor_by_id(state['id'])
                if sensor['interval_sec'] > 0:
                    threading.Thread(target=poll_sensor, args=(sensor["id"],), daemon=True).start()
            else:
                database.update_actor(state['id'], state['field'], val)
                actor = next(a for a in database.list_actors() if a['id'] == state['id'])
                if actor['interval_sec'] > 0:
                    threading.Thread(target=poll_actor, args=(actor['id'],), daemon=True).start()
            bot.send_message(chat_id, "Параметр успешно обновлен!")
            user_states.pop(chat_id)
        return start_handler(message)

    # — удаление устройства —
    if state['action'] == 'delete':
        if state['type'] is None:
            if text == 'Датчик':
                state['type'] = 'sensor'
                items = database.list_sensors()
            else:
                state['type'] = 'actor'
                items = database.list_actors()
            markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
            for itm in items:
                markup.add(types.KeyboardButton(f"{itm['id']}-{itm['name']}"))
            bot.send_message(chat_id, "Выберите объект для удаления:", reply_markup=markup)
            state['step'] = 0
            return
        obj_id = int(text.split('-')[0])
        if state['type'] == 'sensor':
            database.delete_sensor(obj_id)
            bot.send_message(chat_id, "Датчик успешно удален!")
        else:
            database.delete_actor(obj_id)
            bot.send_message(chat_id, "Актор успешно удален!")
        user_states.pop(chat_id)
        return start_handler(message)

    # — отправка управляющего сигнала —
    if state['action'] == 'control':
        if state['step'] == 0:
            aid = int(text.split('-')[0])
            actor = next(a for a in database.list_actors() if a['id'] == aid)
            state['actor'] = actor
            state['step'] = 1
            bot.send_message(chat_id, "Введите задержку в минутах (число):")
            return
        if state['step'] == 1:
            state['delay'] = int(text)
            state['step'] = 2
            bot.send_message(chat_id, "Введите значение сигнала (0-255):")
            return
        if state['step'] == 2:
            state['value'] = int(text)
            state['step'] = 3
            bot.send_message(chat_id, "Введите длительность в секундах (число) или '-' для без возврата:")
            return
        if state['step'] == 3:
            dur = 0 if text == '-' else int(text)
            def activate():
                send_signal(state['actor']['channel'], state['actor']['pin'], state['value'])
            threading.Timer(state['delay'] * 60, activate).start()
            if dur > 0:
                threading.Timer(state['delay'] * 60 + dur, lambda: send_signal(state['actor']['channel'], state['actor']['pin'], 0)).start()
            bot.send_message(chat_id, "Команда запланирована.")
            user_states.pop(chat_id)
        return start_handler(message)

    # — администрирование —
    if state['action'] == 'admin':
        if state['step'] == 0:
            if text == "Добавить администратора":
                state['type'] = 'add'
                state['step'] = 1
                bot.send_message(chat_id, "Введите уникальный юзернейм без @:")
                return
            if text == "Удалить администратора":
                state['type'] = 'del'
                state['step'] = 1
                admins = database.list_admins()
                markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
                for a in admins:
                    markup.add(types.KeyboardButton(a))
                bot.send_message(chat_id, "Выберите администратора для удаления:", reply_markup=markup)
                return
            if text == "Вернуться в главное меню":
                user_states.pop(chat_id)
                return start_handler(message)
        if state['step'] == 1:
            if state['type'] == 'add':
                uname = text if text.startswith('@') else f"@{text}"
                database.add_admin_db(uname)
                bot.send_message(chat_id, f"Администратор {uname} добавлен")
            else:
                database.delete_admin_db(text)
                bot.send_message(chat_id, f"Администратор {text} удален")
            user_states.pop(chat_id)
        return start_handler(message)

@bot.message_handler(commands=['help'])
def help_handler(message):
    bot.send_message(message.chat.id, "Используйте /start для начала.")
    
@bot.message_handler(content_types=['audio', 'video', 'document', 'photo'])
def media_upload_handler(message):
    print("DEBUG: media_upload_handler called")
    print("DEBUG: message.content_type =", message.content_type)
    chat_id = message.chat.id
    state = user_states.get(chat_id)
    print("DEBUG: current state for chat", chat_id, "=", state)

    # Проверяем, в нужном ли мы режиме
    if not state or state.get('action') != 'media' or state.get('media_action') != 'upload':
        print("DEBUG: exiting handler — invalid state or not in upload mode")
        return

    print("DEBUG: upload mode confirmed, download file")

    # Определяем file_id и расширение
    try:
        if message.content_type == 'photo':
            file_id = message.photo[-1].file_id
            ext = '.jpg'
        elif message.content_type == 'video':
            file_id = message.video.file_id
            ext = '.mp4'
        elif message.content_type == 'audio':
            file_id = message.audio.file_id
            ext = '.mp3'
        else:
            file_id = message.document.file_id
            ext = os.path.splitext(message.document.file_name)[1]
        print(f"DEBUG: determined file_id={file_id}, ext={ext}")
    except Exception as e:
        print("ERROR: failed to determine file_id/ext:", e)
        bot.send_message(chat_id, "Ошибка при получении информации о файле.")
        return

    # Получаем файл с Telegram
    try:
        file_info = bot.get_file(file_id)
        print("DEBUG: bot.get_file returned file_path =", file_info.file_path)
        data = bot.download_file(file_info.file_path)
        print("DEBUG: downloaded data, length =", len(data))
    except Exception as e:
        print("ERROR: download failed:", e)
        bot.send_message(chat_id, "Не удалось загрузить файл из Telegram.")
        return

    # Запоминаем в state и запрашиваем имя
    state['downloaded'] = {'data': data, 'ext': ext}
    state['step'] = 3
    bot.send_message(chat_id, "Введите имя файла (без расширения):")
    print("DEBUG: waiting for filename input (step=3)")
    return



if __name__ == '__main__':
    start_polling_all()
    bot.infinity_polling()
