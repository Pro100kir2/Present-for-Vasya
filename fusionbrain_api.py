import requests
import json
import time
import os
from dotenv import load_dotenv
import base64

# Загружаем переменные окружения
load_dotenv()

FUSIONBRAIN_URL = os.getenv('FUSIONBRAIN_API_URL')
API_KEY = os.getenv('FUSIONBRAIN_API_KEY')
SECRET_KEY = os.getenv('FUSIONBRAIN_SECRET_KEY')

AUTH_HEADERS = {
    'X-Key': f'Key {API_KEY}',
    'X-Secret': f'Secret {SECRET_KEY}',
}

class FusionBrainAPI:
    def __init__(self):
        self.pipeline_id = self.get_pipeline_id()

    def get_pipeline_id(self):
        try:
            response = requests.get(FUSIONBRAIN_URL + 'key/api/v1/pipelines', headers=AUTH_HEADERS)
            response.raise_for_status()
            data = response.json()
            return data[0]['id']
        except requests.RequestException as e:
            raise Exception(f"Ошибка при получении pipeline_id: {e}")

    def generate_image(self, prompt, width=1024, height=1024, num_images=1, style=None, negative_prompt=None):
        params = {
            "type": "GENERATE",
            "numImages": num_images,
            "width": width,
            "height": height,
            "generateParams": {
                "query": prompt
            }
        }

        if style:
            params["style"] = style

        if negative_prompt:
            params["negativePromptDecoder"] = negative_prompt

        files = {
            'pipeline_id': (None, self.pipeline_id),
            'params': (None, json.dumps(params), 'application/json')
        }

        try:
            response = requests.post(FUSIONBRAIN_URL + 'key/api/v1/pipeline/run', headers=AUTH_HEADERS, files=files)
            response.raise_for_status()
            data = response.json()
            return data['uuid']
        except requests.RequestException as e:
            raise Exception(f"Ошибка при генерации изображения: {e}")

    def check_status(self, uuid, attempts=10, delay=5):
        for _ in range(attempts):
            try:
                response = requests.get(FUSIONBRAIN_URL + f'key/api/v1/pipeline/status/{uuid}', headers=AUTH_HEADERS)
                response.raise_for_status()
                data = response.json()
                if data['status'] == 'DONE':
                    return data['result']['files']
                time.sleep(delay)
            except requests.RequestException as e:
                raise Exception(f"Ошибка при проверке статуса: {e}")
        return None

def save_base64_image(base64_str, filename):
    # Декодируем base64 строку в бинарные данные
    image_data = base64.b64decode(base64_str)

    # Сохраняем данные в файл
    with open(filename, 'wb') as f:
        f.write(image_data)
    print(f"Изображение сохранено как {filename}")