from flask import Flask, render_template, request, jsonify, flash, redirect, url_for, session, send_from_directory
from werkzeug.security import generate_password_hash, check_password_hash
from fusionbrain_api import FusionBrainAPI
from contextlib import closing
from dotenv import load_dotenv
import mysql.connector
import threading
import requests
import logging
import urllib3
import difflib
import json
import time
import os
import re

load_dotenv()
logging.basicConfig(level=logging.INFO)

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
SECRET_KEY = os.environ.get('SECRET_KEY')

MYSQL_USER = os.getenv('MYSQL_USER')
MYSQL_PASSWORD = os.getenv('MYSQL_PASSWORD')
MYSQL_HOST = os.getenv('MYSQL_HOST')
MYSQL_DB = os.getenv('MYSQL_DB')


def get_db_connection():
    connection = mysql.connector.connect(
        host=MYSQL_HOST,
        user=MYSQL_USER,
        password=MYSQL_PASSWORD,
        database=MYSQL_DB
    )
    return connection


def fetch_initial_token():
    try:
        connection = get_db_connection()
        cursor = connection.cursor()
        cursor.execute("SELECT initial_token FROM tokens LIMIT 1;")
        token = cursor.fetchone()
        cursor.close()
        connection.close()
        if token:
            print("📌 Initial Token:", token[0])
            return token[0]
        else:
            print("❌ Initial Token не найден в базе данных.")
            return None
    except Exception as e:
        print("⚠ Ошибка при подключении к базе данных:", e)
        return None


def refresh_token():
    url = "https://ngw.devices.sberbank.ru:9443/api/v2/oauth"
    payload = {'scope': 'GIGACHAT_API_PERS'}
    headers = {
        'Content-Type': 'application/x-www-form-urlencoded',
        'Accept': 'application/json',
        'RqUID': '77644f17-cf3d-4604-8420-decd56e43e6d',
        'Authorization': f'Basic {SECRET_KEY}'
    }

    try:
        response = requests.post(url, headers=headers, data=payload, verify=False)
        if response.status_code == 200:
            new_token = response.json().get('access_token')
            if new_token:
                conn = get_db_connection()
                cursor = conn.cursor()
                cursor.execute("UPDATE tokens SET initial_token = %s WHERE id = 1;", (new_token,))
                conn.commit()
                conn.close()
                print("🔄 Initial Token обновлён!")
                return new_token
        print(f"❌ Ошибка получения токена: {response.status_code}")
    except requests.RequestException as e:
        print(f"⚠ Ошибка сети при получении токена: {str(e)}")
    return None


def token_updater():
    while True:
        refresh_token()
        time.sleep(1650)


refresh_token()

threading.Thread(target=token_updater, daemon=True).start()

app = Flask(__name__)
app.secret_key = 'your_secret_key'
app.config['SECRET_KEY'] = SECRET_KEY

# Создаём экземпляр API при старте
fusionbrain = FusionBrainAPI()
generation_tasks = {}  # Словарь для хранения статусов
conversation_history = []


def get_custom_reply(question):
    normalized_question = re.sub(r'\W+', ' ', question.strip().lower())
    custom_replies = {
        "как меня зовут": "Что-то мне подсказывает что твоё имя то - которым тебя назвали родители",
        "Как меня зовут": "Что-то мне подсказывает что твоё имя то - которым тебя назвали родители",
        "как меня зовут?": "Что-то мне подсказывает что твоё имя то - которым тебя назвали родители",
        "как меня звать": "Что-то мне подсказывает что твоё имя то - которым тебя назвали родители",
        "Как меня зовут?": "Что-то мне подсказывает что твоё имя то - которым тебя назвали родители",
        "Как меня звать": "Что-то мне подсказывает что твоё имя то - которым тебя назвали родители",
        "как меня звать?": "Что-то мне подсказывает что твоё имя то - которым тебя назвали родители",
        "Как меня звать?": "Что-то мне подсказывает что твоё имя то - которым тебя назвали родители",
        "какой лучший язык программирования": "Конечно, тот, которым ты уже зарабатываешь!",
        "какой лучший язык программирования?": "Конечно, тот, которым ты уже зарабатываешь!",
        "лучший язык программирования": "Конечно, тот, которым ты уже зарабатываешь!",
        "как стать программистом": "Начните с основ, практикуйтесь ежедневно и не бойтесь ошибок.",
        "что делать чтобы стать программистом": "Начните с основ, практикуйтесь ежедневно и не бойтесь ошибок.",
        "зачем изучать алгоритмы": "Алгоритмы помогают решать задачи эффективно и понимают фундаментальные принципы программирования.",
        "как выбрать первый язык программирования": "Выбирайте язык, который подходит под ваши цели и интересы. Python — отличный старт для новичков.",
        "как писать чистый код": "Следуйте принципам DRY (Don't Repeat Yourself) и KISS (Keep It Simple, Stupid). Чистый код легко читается и поддерживается.",
        "как бороться с прокрастинацией": "Разбейте большие задачи на маленькие и выполняйте их постепенно. Маленькие победы мотивируют продолжать.",
        "как выбрать специализацию в it": "Исследуйте рынок труда, узнавайте о перспективных направлениях и выбирайте то, что вас вдохновляет.",
        "как улучшить навыки общения": "Практикуйте активное слушание, задавайте уточняющие вопросы и старайтесь быть внимательными к собеседнику.",
        "как справиться со стрессом на работе": "Найдите баланс между работой и отдыхом, занимайтесь спортом и медитацией, общайтесь с коллегами.",
        "как управлять временем": "Используйте техники тайм-менеджмента, такие как метод Помодоро или списки дел. Планируйте день заранее.",
        "как подготовиться к собеседованию": "Изучайте требования вакансии, готовьтесь к техническим вопросам и практикуйтесь в решении задач.",
        "как развивать креативность": "Читайте книги, смотрите фильмы, путешествуйте и общайтесь с разными людьми. Новые впечатления стимулируют креативность.",
        "как справляться с выгоранием": "Делайте перерывы, переключайтесь на другие виды деятельности, находите время для хобби и отдыха.",
        "как выбрать курсы для изучения программирования": "Определите свои цели и уровень подготовки, читайте отзывы и выбирайте курсы с практическими заданиями.",
        "как написать резюме": "Акцентируйте внимание на достижениях, используйте ключевые слова из описания вакансии и будьте честными.",
        "как готовиться к экзаменам": "Составляйте план подготовки, разбивайте материал на части и регулярно повторяйте пройденное.",
        "как найти работу мечты": "Определите свои ценности и цели, исследуйте компании, которые соответствуют вашим интересам, и активно ищите возможности.",
        "как развить уверенность в себе": "Ставьте перед собой достижимые цели, отмечайте свои успехи и окружайте себя поддерживающими людьми.",
        "как справляться с критикой": "Слушайте конструктивную критику, анализируйте её и используйте для улучшения своих навыков.",
        "как развивать эмоциональный интеллект": "Учитесь распознавать и понимать эмоции свои и окружающих, развивайте эмпатию и саморефлексию.",
        "как поддерживать мотивацию": "Ставьте небольшие цели, празднуйте достижения и находите вдохновение в примерах успешных людей.",
        "как развивать лидерские качества": "Практикуйтесь в принятии решений, развивайте коммуникативные навыки и умение вдохновлять команду.",
        "как справляться с неуверенностью в себе": "Признавайте свои страхи, работайте над самооценкой и развивайте уверенность через опыт и обучение.",
        "как планировать карьеру": "Оценивайте свои сильные стороны, исследуйте рынок труда и ставьте долгосрочные цели, которые помогут развиваться.",
        "как справляться с конфликтами на работе": "Будьте открытыми к диалогу, уважайте мнения других и стремитесь находить компромиссные решения.",
        "как улучшить навыки публичных выступлений": "Практикуйтесь перед зеркалом, записывайте себя на видео, изучайте риторические приёмы и получайте обратную связь.",
        "как поддерживать продуктивность на высоком уровне": "Используйте техники управления энергией, делайте регулярные перерывы и сосредотачивайтесь на приоритетных задачах.",
        "как выбрать наставника": "Ищите профессионала с опытом в вашей области, который готов делиться знаниями и поддерживает ваш рост.",
        "как строить эффективные команды": "Нанимайте людей с разнообразными навыками, создавайте культуру доверия и поощряйте открытое общение.",
        "как развивать стратегическое мышление": "Анализируйте ситуации, учитывайте долгосрочные последствия и разрабатывайте планы на основе данных и прогнозов.",
        "как справляться с давлением дедлайнов": "Планируйте время заранее, делегируйте задачи и оставляйте запас на непредвиденные обстоятельства.",
        "как развивать навыки анализа данных": "Учите основы статистики, осваивайте инструменты анализа данных, такие как Excel, SQL и Python.",
        "как развивать навыки ведения переговоров": "Тренируйтесь в активных переговорах, изучайте техники убеждения и учитывайте интересы обеих сторон.",
        "как справляться с негативной обратной связью": "Принимайте критику объективно, рассматривайте её как возможность для роста и корректировки стратегии.",
        "как развивать навыки управления проектами": "Осваивайте методологии управления проектами, такие как Agile и Scrum, и практикуйтесь в планировании и контроле выполнения задач.",
        "как выбирать направления для развития карьеры": "Анализируйте тренды рынка, оценивайте свои интересы и способности, консультируйтесь с экспертами и смотрите на долгосрочную перспективу.",
        "как справляться с неопределённостью": "Разработайте план действий на случай различных сценариев, сохраняйте гибкость и адаптируйтесь к изменениям.",
        "как развивать навыки принятия решений": "Собирайте информацию, взвешивайте варианты, принимайте решения на основе фактов и учитесь на ошибках.",
        "как поддерживать баланс между работой и личной жизнью": "Устанавливайте чёткие границы, выделяйте время для семьи и увлечений, управляйте своим временем осознанно.",
        "как развивать навыки самоорганизации": "Создавайте расписание, устанавливайте приоритеты, используйте календари и списки задач, контролируйте выполнение планов.",
        "как справляться с синдромом самозванца": "Признавайте свои достижения, сравнивайте себя с собой вчерашним, а не с другими, и развивайте уверенность в своих силах.",
        "как выбирать профессию": "Исследуйте разные профессии, проходите тесты на профориентацию, получайте консультации специалистов и пробуйте стажировки.",
        "как справляться с перфекционизмом": "Установите реалистичные стандарты, фокусируйтесь на процессе, а не только на результате, и позволяйте себе ошибки.",
        "как развивать навыки работы в команде": "Работайте над коммуникативными навыками, учитесь выслушивать коллег, поддерживайте коллективную работу и уважайте мнение каждого члена команды.",
        "как справляться с профессиональным выгоранием": "Возьмите паузу, пересмотрите свои приоритеты, найдите поддержку среди коллег и друзей, и заботьтесь о своём физическом и психическом здоровье.",
        "как справляться с профессиональными изменениями": "Будьте открыты новым возможностям, продолжайте учиться и адаптируйтесь к меняющимся условиям, воспринимая изменения как шанс для роста.",
        "как развивать навыки критического мышления": "Читайте разнообразные источники информации, анализируйте аргументы, задавайте вопросы и рассматриваете проблемы с разных точек зрения.",
        "как справляться с культурными различиями на работе": "Уважайте разнообразие, изучайте культуры коллег, проявляйте эмпатию и будьте готовы адаптироваться к различным стилям общения и поведения.",
        "как справляться с многозадачностью": "Организуйте своё время, расставляйте приоритеты, делегируйте задачи и сосредотачивайтесь на одной задаче за раз.",
        "как справляться с недовольством начальства": "Открыто обсуждайте проблемы, предлагайте решения, показывайте готовность к улучшению и демонстрируйте профессионализм.",
        "как справляться с конкуренцией на рынке труда": "Развивайте уникальные навыки, следите за трендами, создавайте портфолио и постоянно совершенствуйте свои компетенции.",
        "как справляться с чувством одиночества на удалённой работе": "Поддерживайте социальные связи, участвуйте в онлайн-сообществах, организовывайте виртуальные встречи и не забывайте о личном общении.",
        "как справляться с высокими ожиданиями": "Четко определяйте свои цели и приоритеты, учитесь говорить \"нет\" избыточным требованиям и реалистично оценивайте свои возможности.",
        "как справляться с перегрузкой информацией": "Фильтруйте источники информации, используйте системы управления знаниями, такие как Evernote или Notion, и ограничивайте время на потребление новостей.",
    }
    return custom_replies.get(normalized_question, None)


def save_message_to_db(user_message, assistant_content):
    user_id = session.get('user_id')
    if user_id:
        try:
            connection = get_db_connection()
            cursor = connection.cursor()

            cursor.execute("INSERT INTO messages (user_id, user_message, assistant_message) VALUES (%s, %s, %s)",
                           (user_id, user_message, assistant_content))
            connection.commit()
            cursor.close()
            connection.close()
        except mysql.connector.Error as err:
            print(f"⚠ Ошибка сохранения в БД: {err}")


def get_chat_completions(user_message, conversation_history, max_retries=3):
    url = "https://gigachat.devices.sberbank.ru/api/v1/chat/completions"

    auth_token = fetch_initial_token()

    if not auth_token:
        return "Ошибка: Токен не найден.", conversation_history

    if not any(msg['role'] == 'system' for msg in conversation_history):
        conversation_history.insert(0, {
            "role": "system",
            "content": "Ты очень мудрый и спокойный. Твой стиль общения - отетить за вопрос и сказать как бы поступил ты. Тебя зовут ассистент Василий и тебя создал Лупанов Кирилл Александрович "
        })

    custom_reply = get_custom_reply(user_message)
    if custom_reply:
        return custom_reply, conversation_history

    conversation_history.append({"role": "user", "content": user_message})

    payload = json.dumps({"model": "GigaChat-2", "messages": conversation_history})
    headers = {"Authorization": f"Bearer {auth_token}", "Content-Type": "application/json"}

    attempt = 0
    while attempt < max_retries:
        try:
            response = requests.post(url, headers=headers, data=payload, timeout=10, verify=False)

            if response.status_code == 200:
                assistant_content = response.json().get("choices", [{}])[0].get("message", {}).get("content", "")
                conversation_history.append({"role": "assistant", "content": assistant_content})
                save_message_to_db(user_message, assistant_content)
                return assistant_content, conversation_history
            elif response.status_code == 401:

                auth_token = refresh_token()
                if auth_token:
                    logging.info("🔄 Новый токен получен!")
                else:
                    return "Ошибка: Не удалось обновить токен.", conversation_history
            else:
                return f"Ошибка API: {response.status_code} - {response.text}", conversation_history

        except requests.RequestException as e:
            logging.error(f"⚠ Ошибка при запросе: {str(e)}")
            attempt += 1
            if attempt >= max_retries:
                return f"Ошибка при получении ответа после {max_retries} попыток: {str(e)}", conversation_history

    return "Не удалось получить ответ после нескольких попыток.", conversation_history


def get_user_messages():
    user_id = session.get('user_id')
    if user_id:
        try:
            with closing(get_db_connection()) as connection:
                with closing(connection.cursor()) as cursor:
                    cursor.execute(
                        "SELECT user_message, assistant_message, timestamp FROM messages WHERE user_id = %s ORDER BY timestamp ASC",
                        (user_id,))
                    messages = cursor.fetchall()

            logging.info(f"Получены данные из базы: {messages}")

            conversation_history = []
            for user_msg, assistant_msg, timestamp in messages:
                conversation_history.append({"role": "user", "content": user_msg})
                conversation_history.append({"role": "assistant", "content": assistant_msg})

            logging.info(f"Получено {len(messages)} сообщений пользователя из базы данных.")
            return conversation_history
        except mysql.connector.Error as err:
            logging.error(f"⚠ Ошибка при получении сообщений из БД: {err}")
    return []


@app.route('/')
def index():
    messages = get_user_messages()
    print(messages)
    return render_template('chat.html', messages=messages)


@app.route('/static2/<filename>')
def static2_files(filename):
    return send_from_directory('static2', filename)


@app.route('/static/<filename>')
def static_files(filename):
    response = send_from_directory('static', filename)
    response.cache_control.no_cache = True
    response.cache_control.no_store = True
    return response


@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form['name']
        email = request.form['email']
        password = request.form['password']
        password_hash = generate_password_hash(password)

        try:
            connection = get_db_connection()
            cursor = connection.cursor()

            cursor.execute("SELECT * FROM users WHERE email = %s", (email,))
            existing_user = cursor.fetchone()

            if existing_user:
                return "Пользователь с таким email уже существует.", 400

            cursor.execute("INSERT INTO users (name, email, password_hash) VALUES (%s, %s, %s)",
                           (username, email, password_hash))
            connection.commit()
            cursor.close()
            connection.close()
            return redirect(url_for('login'))
        except mysql.connector.Error as err:
            return f"Ошибка базы данных: {err}", 500
    return render_template('register.html')


@app.route('/login', methods=['GET', 'POST'])
def login():
    print(f"Сессия: {session}")
    if request.method == 'POST':
        username = request.form.get('name')
        password = request.form.get('password')

        if not username or not password:
            return render_template('login.html', error="Заполните все поля", username=username)

        try:
            connection = get_db_connection()
            cursor = connection.cursor()

            cursor.execute("SELECT * FROM users WHERE name = %s", (username,))
            user = cursor.fetchone()

            if user and check_password_hash(user[3], password):
                session['user_id'] = user[0]
                return redirect(url_for('index'))
            else:
                return render_template('login.html', error="Неверное имя пользователя или пароль", username=username)
        except mysql.connector.Error as err:
            return render_template('login.html', error=f"Ошибка базы данных: {err}", username=username)

    return render_template('login.html')


@app.route('/clean', methods=['POST'])
def clear_conversation():
    user_id = session.get('user_id')
    if not user_id:
        flash("Вы не авторизованы.", "error")
        return redirect(url_for('index'))

    try:
        with closing(get_db_connection()) as connection:
            with closing(connection.cursor()) as cursor:
                cursor.execute("DELETE FROM messages WHERE user_id = %s", (user_id,))
                connection.commit()
        logging.info(f"✅ Удалены все сообщения пользователя {user_id} из базы.")
        flash("Переписка успешно очищена.", "success")
    except mysql.connector.Error as err:
        logging.error(f"⚠ Ошибка при удалении сообщений: {err}")
        flash("Ошибка при очистке переписки.", "error")

    return redirect(url_for('index'))


@app.route('/setting', methods=['GET', 'POST'])
def setting():
    user_id = session.get('user_id')

    if not user_id:
        return redirect(url_for('login'))

    try:
        connection = get_db_connection()
        cursor = connection.cursor()

        cursor.execute("SELECT name, email FROM users WHERE id = %s", (user_id,))
        user = cursor.fetchone()

        if not user:
            return "Пользователь не найден.", 404

        if request.method == 'POST':

            new_name = request.form['name']
            new_email = request.form['email']
            new_password = request.form['password']
            password_hash = None

            if new_password:
                password_hash = generate_password_hash(new_password)

            if password_hash:
                cursor.execute("UPDATE users SET name = %s, email = %s, password_hash = %s WHERE id = %s",
                               (new_name, new_email, password_hash, user_id))
            else:
                cursor.execute("UPDATE users SET name = %s, email = %s WHERE id = %s",
                               (new_name, new_email, user_id))

            connection.commit()
            cursor.close()
            connection.close()
            return redirect(url_for('index'))

        return render_template('setting.html', user=user)

    except mysql.connector.Error as err:
        return f"Ошибка базы данных: {err}", 500

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('index'))

def format_response(text, is_code=False, is_list=False):
    if is_code:
        return f"```python\n{text}\n```"
    elif is_list:
        items = text.split(", ")
        formatted_list = "\n".join([f"{i + 1}. {item}" for i, item in enumerate(items)])
        return formatted_list
    return text

@app.route('/send_message', methods=['POST'])
def send_message():
    global conversation_history
    user_message = request.json.get("message", "").strip()
    if not user_message:
        return jsonify({"error": "Пустой запрос"}), 400
    response, conversation_history = get_chat_completions(user_message, conversation_history)
    return jsonify({"response": response})

@app.route('/image_chat', methods=['Get','POST'])
def image_chat():
    return render_template('image_chat.html')

@app.route('/generate-image', methods=['POST'])
def generate_image():
    """
    Маршрут для запуска генерации изображения через FusionBrain API.
    Отвечает сразу UUID задачи.
    """
    data = request.get_json()

    if not data:
        return jsonify({'error': 'Пустой запрос.'}), 400

    prompt = data.get('prompt')
    width = data.get('width', 1024)
    height = data.get('height', 1024)
    style = data.get('style')
    negative_prompt = data.get('negative_prompt')

    if not prompt:
        return jsonify({'error': 'Поле prompt обязательно для генерации.'}), 400

    try:
        # Только запускаем задачу
        uuid = fusionbrain.generate_image(
            prompt=prompt,
            width=width,
            height=height,
            num_images=1,
            style=style,
            negative_prompt=negative_prompt
        )

        # Сразу возвращаем UUID, без ожидания генерации
        return jsonify({'uuid': uuid})
    except Exception as e:
        return jsonify({'error': f'Ошибка при запуске генерации: {str(e)}'}), 500

@app.route('/check-status', methods=['GET'])
def check_status():
    """
    Проверка статуса готовности изображения по UUID.
    """
    uuid = request.args.get('uuid')

    if not uuid:
        return jsonify({'error': 'UUID обязателен для проверки статуса.'}), 400

    try:
        files = fusionbrain.check_status(uuid)

        if files:
            return jsonify({'ready': True, 'images': files})
        else:
            return jsonify({'ready': False})
    except Exception as e:
        return jsonify({'error': f'Ошибка при проверке статуса: {str(e)}'}), 500

@app.route('/yandex_dffe98de3ad223d3.html', methods=["GET"])
def yandex_dffe98de3ad223d3():
    return render_template('yandex_dffe98de3ad223d3.html')

@app.route('/sitemap.xml', methods=['GET'])
def sitemap():
    return render_template('/sitemap.xml')

@app.route('/favicon.ico', methods=['GET'])
def vasia():
    return send_from_directory('static', "favicon.ico")

@app.route('/robots.txt', methods=['GET'])
def robots():
    return send_from_directory(os.getcwd(), 'robots.txt')

if __name__ == '__main__':
    refresh_token()
    app.run(debug=True, port=8000)
