import sqlite3
import connect
from contextlib import closing

def get_connection(db_path: str = "smart_home.db") -> sqlite3.Connection:
    """Открывает соединение с базой и настраивает row_factory."""
    conn = sqlite3.connect(db_path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def init_db(db_path: str = "smart_home.db") -> None:
    """Инициализирует все необходимые таблицы."""
    with closing(get_connection(db_path)) as conn:
        c = conn.cursor()

        # Таблица сенсоров
        c.execute('''
            CREATE TABLE IF NOT EXISTS sensors (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                description TEXT,
                channel INTEGER,
                pin INTEGER,
                interval_sec INTEGER
            )

        ''')

        # Таблица акторов: теперь с полями value и duration
        c.execute('''
            CREATE TABLE IF NOT EXISTS actors (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                description TEXT,
                channel INTEGER,
                pin INTEGER,
                interval_sec INTEGER,
                value INTEGER DEFAULT 0,
                duration INTEGER DEFAULT 0
            )
        ''')

        # Таблица данных сенсоров
        c.execute('''
            CREATE TABLE IF NOT EXISTS sensors_data (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                sensor_id INTEGER,
                timestamp DATETIME DEFAULT (datetime('now','localtime')),
                value REAL,
                FOREIGN KEY(sensor_id) REFERENCES sensors(id)
            )
        ''')

        # Таблица сценариев
        c.execute('''
            CREATE TABLE IF NOT EXISTS scripts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL UNIQUE,
                sensor_id INTEGER NOT NULL,
                threshold REAL NOT NULL,
                actor_id INTEGER NOT NULL,
                actor_value INTEGER NOT NULL,
                type_of_script INTEGER NOT NULL,  -- 1: ≥threshold, 0: ≤threshold
                FOREIGN KEY(sensor_id) REFERENCES sensors(id),
                FOREIGN KEY(actor_id)  REFERENCES actors(id)
            )
        ''')




        # Таблица администраторов
        c.execute('''
            CREATE TABLE IF NOT EXISTS admins (
                username TEXT PRIMARY KEY
            )
        ''')
        # Дефолтный админ
        c.execute('INSERT OR IGNORE INTO admins (username) VALUES (?)', ("@Krinzovnik88",))

        conn.commit()

# ————— Функции для работы с сенсорами —————

def add_sensor(data: dict, db_path: str = "smart_home.db") -> int:
    """Добавляет новый сенсор и возвращает его id."""
    with closing(get_connection(db_path)) as conn:
        c = conn.cursor()
        c.execute('''
            INSERT INTO sensors
                (name, description, channel, pin, interval_sec)
            VALUES (?, ?, ?, ?, ?)
        ''', (
            data["name"], data["description"],
            data["channel"], data["pin"],
            data["interval_sec"]
        ))
        conn.commit()
        return c.lastrowid


def list_sensors(db_path: str = "smart_home.db") -> list[sqlite3.Row]:
    """Возвращает список всех сенсоров."""
    with closing(get_connection(db_path)) as conn:
        c = conn.cursor()
        c.execute("SELECT * FROM sensors")
        return c.fetchall()


def get_sensor_by_id(sensor_id: int, db_path: str = "smart_home.db") -> sqlite3.Row | None:
    """Возвращает запись сенсора по его ID."""
    with closing(get_connection(db_path)) as conn:
        c = conn.cursor()
        c.execute("SELECT * FROM sensors WHERE id = ?", (sensor_id,))
        return c.fetchone()
    
def get_actor_by_id(actor_id: int, db_path: str = "smart_home.db") -> sqlite3.Row | None:
    """Возвращает запись актора по его ID."""
    with closing(get_connection(db_path)) as conn:
        c = conn.cursor()
        c.execute("SELECT * FROM actors WHERE id = ?", (actor_id,))
        return c.fetchone()

def update_sensor(sensor_id: int, field: str, value, db_path: str = "smart_home.db") -> None:
    """Обновляет одно поле сенсора."""
    with closing(get_connection(db_path)) as conn:
        c = conn.cursor()
        c.execute(
            f"UPDATE sensors SET {field} = ? WHERE id = ?",
            (value, sensor_id)
        )
        conn.commit()


def delete_sensor(sensor_id: int, db_path: str = "smart_home.db") -> None:
    """Удаляет сенсор и все его показания."""
    with closing(get_connection(db_path)) as conn:
        c = conn.cursor()
        c.execute("DELETE FROM sensors WHERE id = ?", (sensor_id,))
        c.execute("DELETE FROM sensors_data WHERE sensor_id = ?", (sensor_id,))
        conn.commit()


def get_sensor_data(sensor_id: int, minutes: int, db_path: str = "smart_home.db") -> list[sqlite3.Row]:
    """Возвращает показания за последние `minutes` минут."""
    with closing(get_connection(db_path)) as conn:
        c = conn.cursor()
        c.execute('''
            SELECT timestamp, value
              FROM sensors_data
             WHERE sensor_id = ?
               AND timestamp >= datetime('now', ?)
             ORDER BY timestamp
        ''', (sensor_id, f"-{minutes} minutes"))
        return c.fetchall()


def get_last_sensor_reading(sensor_id: int, db_path: str = "smart_home.db") -> sqlite3.Row | None:
    """Возвращает последнее показание сенсора."""
    with closing(get_connection(db_path)) as conn:
        c = conn.cursor()
        c.execute('''
            SELECT timestamp, value
              FROM sensors_data
             WHERE sensor_id = ?
             ORDER BY timestamp DESC
             LIMIT 1
        ''', (sensor_id,))
        return c.fetchone()

# ————— Функции для работы с актёрами —————

def add_actor(data: dict, db_path: str = "smart_home.db") -> int:
    """Добавляет нового актора и возвращает его id."""
    with closing(get_connection(db_path)) as conn:
        c = conn.cursor()
        # duration и value могут отсутствовать в data
        duration = data.get("duration", 0)
        value = data.get("value", 0)
        c.execute('''
            INSERT INTO actors
                (name, description, channel, pin, interval_sec, value, duration)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        ''', (
            data["name"], data["description"],
            data["channel"], data["pin"],
            data.get("interval_sec", 0), value, duration
        ))
        conn.commit()
        return c.lastrowid


def list_actors(db_path: str = "smart_home.db") -> list[sqlite3.Row]:
    """Возвращает список всех акторов."""
    with closing(get_connection(db_path)) as conn:
        c = conn.cursor()
        c.execute("SELECT * FROM actors")
        return c.fetchall()


def update_actor(actor_id: int, field: str, value, db_path: str = "smart_home.db") -> None:
    """Обновляет одно поле актора."""
    with closing(get_connection(db_path)) as conn:
        c = conn.cursor()
        c.execute(
            f"UPDATE actors SET {field} = ? WHERE id = ?",
            (value, actor_id)
        )
        conn.commit()


def delete_actor(actor_id: int, db_path: str = "smart_home.db") -> None:
    """Удаляет актора."""
    with closing(get_connection(db_path)) as conn:
        c = conn.cursor()
        c.execute("DELETE FROM actors WHERE id = ?", (actor_id,))
        conn.commit()

# ————— Функции для работы с данными сенсоров по channel/pin —————

def add_data(channel: int, pin: int, value: float, db_path: str = "smart_home.db") -> None:
    """
    Находит сенсор по (channel, pin) и записывает в sensors_data.
    Ничего не делает, если сенсор не найден.
    """
    with closing(get_connection(db_path)) as conn:
        c = conn.cursor()
        c.execute(
            "SELECT id FROM sensors WHERE channel = ? AND pin = ?",
            (channel, pin)
        )
        row = c.fetchone()
        if row:
            sensor_id = row["id"]
            c.execute(
                "INSERT INTO sensors_data (sensor_id, value) VALUES (?, ?)",
                (sensor_id, value)
            )
            conn.commit()


def get_data(channel: int, pin: int) -> float:
    value=(connect.sens(channel,pin))
    add_data(channel, pin, value)
    return value

# ————— Функции для работы с администраторами —————

def list_admins(db_path: str = "smart_home.db") -> list[str]:
    """Возвращает список всех администраторов."""
    with closing(get_connection(db_path)) as conn:
        c = conn.cursor()
        c.execute("SELECT username FROM admins")
        return [row["username"] for row in c.fetchall()]


def add_admin_db(username: str, db_path: str = "smart_home.db") -> None:
    """Добавляет нового администратора."""
    with closing(get_connection(db_path)) as conn:
        c = conn.cursor()
        c.execute(
            "INSERT OR IGNORE INTO admins (username) VALUES (?)",
            (username,)
        )
        conn.commit()


def delete_admin_db(username: str, db_path: str = "smart_home.db") -> None:
    """Удаляет администратора."""
    with closing(get_connection(db_path)) as conn:
        c = conn.cursor()
        c.execute(
            "DELETE FROM admins WHERE username = ?",
            (username,)
        )
        conn.commit()


def add_script(data, db_path="smart_home.db") -> int:
    with closing(get_connection(db_path)) as conn:
        c = conn.cursor()
        c.execute('''
            INSERT INTO scripts
              (name, sensor_id, threshold, actor_id, actor_value, type_of_script)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (
            data["name"], data["sensor_id"], data["threshold"],
            data["actor_id"], data["actor_value"],
            1 if data["type_of_script"] else 0
        ))
        conn.commit()
        return c.lastrowid


def list_scripts(db_path: str = "smart_home.db") -> list[sqlite3.Row]:
    """Вернуть все сценарии."""
    with closing(get_connection(db_path)) as conn:
        c = conn.cursor()
        c.execute("SELECT * FROM scripts")
        return c.fetchall()
    
def list_scripts_by_sensor(sensor_id: int, db_path: str = "smart_home.db") -> list[sqlite3.Row]:
    """Все сценарии для данного датчика."""
    with closing(get_connection(db_path)) as conn:
        c = conn.cursor()
        c.execute("SELECT * FROM scripts WHERE sensor_id = ?", (sensor_id,))
        return c.fetchall()


def delete_script(script_id: int, db_path: str = "smart_home.db") -> None:
    """Удалить сценарий."""
    with closing(get_connection(db_path)) as conn:
        c = conn.cursor()
        c.execute("DELETE FROM scripts WHERE id = ?", (script_id,))
        conn.commit()

def get_script_by_id(script_id: int, db_path: str = "smart_home.db") -> sqlite3.Row | None:
    """Вернуть сценарий по ID."""
    with closing(get_connection(db_path)) as conn:
        c = conn.cursor()
        c.execute("SELECT * FROM scripts WHERE id = ?", (script_id,))
        return c.fetchone()
def update_script(script_id: int, field: str, value, db_path="smart_home.db"):
    with closing(get_connection(db_path)) as conn:
        c = conn.cursor()
        c.execute(f"UPDATE scripts SET {field} = ? WHERE id = ?", (value, script_id))
        conn.commit()
