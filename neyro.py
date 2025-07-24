import os
import time
import base64
import uuid
import requests
from PIL import Image

# ==============================
#  1) ВАШИ ПАРАМЕТРЫ
# ==============================

# → Секретный API-ключ (Secret key) вашего сервисного аккаунта
API_KEY = "The secret API key of your Yandex Cloud service account"
# :contentReference[oaicite:6]{index=6}

# → ID каталога (Folder ID) из консоли Yandex Cloud
FOLDER_ID = "catalog id from Yandex Cloud"
# :contentReference[oaicite:7]{index=7}

# Асинхронный endpoint для генерации
API_URL = "https://llm.api.cloud.yandex.net/foundationModels/v1/imageGenerationAsync"
# :contentReference[oaicite:8]{index=8}

# Корректный endpoint для опроса статуса операций
OPERATIONS_URL = "https://operation.api.cloud.yandex.net/operations"
# :contentReference[oaicite:9]{index=9}

# Папка для сохранения изображений
OUTPUT_DIR = "home/files"


def generate_image(imya, prompt: str, seed: int = None) -> str:
    # создаём каталог, если нужно
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    # Тело POST-запроса
    payload = {
        "modelUri": f"art://{FOLDER_ID}/yandex-art/latest",
        # :contentReference[oaicite:10]{index=10}
        "generationOptions": {
            "seed": seed or (uuid.uuid4().int & ((1 << 32) - 1)),
            "aspectRatio": {"widthRatio": "1", "heightRatio": "1"}
        },
        "messages": [{"weight": "1", "text": prompt}]
    }
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Api-Key {API_KEY}"
    }

    # 1) Запускаем генерацию
    resp = requests.post(API_URL, headers=headers, json=payload)
    resp.raise_for_status()
    operation_id = resp.json()["id"]
    print(f"Операция запущена, id = {operation_id}")

    # 2) Ожидание завершения (polling)
    while True:
        time.sleep(5)  # подождать 5 секунд
        status = requests.get(f"{OPERATIONS_URL}/{operation_id}", headers=headers)
        status.raise_for_status()
        data = status.json()
        if data.get("done"):
            # 3) Раскодируем Base64 → байты → сохраняем
            b64img = data["response"]["image"]
            img_bytes = base64.b64decode(b64img)
            filename = f"{imya}.jpeg"
            filepath = os.path.join(OUTPUT_DIR, filename)
            with open(filepath, "wb") as f:
                f.write(img_bytes)
            print(f"Изображение сохранено: {filepath}")
            return filepath
        else:
            print("Ещё не готово, проверяем снова через 5 секунд...")


def sozdanie(prompt_text, nazvanie):
    try:
        generate_image(nazvanie, prompt_text)
    except Exception as e:
        print(f"Ошибка при генерации: {e}")
