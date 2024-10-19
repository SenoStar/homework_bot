import os
import sys
import requests
import logging
import time
from dotenv import load_dotenv
from telebot import TeleBot
from exceptions import ApiError

# Настройка ошибок.
logging.basicConfig(
    level=logging.DEBUG,
    filename='main.log',
    format='%(asctime)s %(levelname)s %(message)s'
)

load_dotenv()

PRACTICUM_TOKEN = os.getenv('PRACTICUM_TOKEN')
TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN')
TELEGRAM_CHAT_ID = os.getenv('TELEGRAM_CHAT_ID')

SECONDS_IN_20_DAYS = 20 * 24 * 60 * 60

RETRY_PERIOD = 600
ENDPOINT = 'https://practicum.yandex.ru/api/user_api/homework_statuses/'
HEADERS = {'Authorization': f'OAuth {PRACTICUM_TOKEN}'}

HOMEWORK_VERDICTS = {
    'approved': 'Работа проверена: ревьюеру всё понравилось. Ура!',
    'reviewing': 'Работа взята на проверку ревьюером.',
    'rejected': 'Работа проверена: у ревьюера есть замечания.'
}

RESPONSE_KEYS = ('homeworks', 'current_date')

# Название нужной работы.
HOMEWORK_NAME = 'SenoStar__django_testing'


def check_tokens():
    """Проверка доступности переменных окружения."""
    tokens = {
        'PRACTICUM_TOKEN': PRACTICUM_TOKEN,
        'TELEGRAM_TOKEN': TELEGRAM_TOKEN,
        'TELEGRAM_CHAT_ID': TELEGRAM_CHAT_ID,
    }

    for token_key, token_value in tokens.items():
        if token_value is None:
            logging.critical(
                f'Отсутствует обязательная переменная окружения: {token_key}'
            )
            return False
    else:
        logging.info('Все нужные токены есть')
        return True


def get_api_answer(timestamp):
    """Запрос к единственному эндпоинту API-сервиса."""

    payload = {'from_date': timestamp}
    logging.info(f'Попытка отправки GET-запроса по {ENDPOINT}, с параметрами: {payload}')
    
    try:
        response = requests.get(
            ENDPOINT,
            headers=HEADERS,
            params=payload
            )
    except requests.RequestException:
        raise ApiError(f'Ошибка API. Код ответа: {response.status_code}.')

    # Проверка кода состояния (ОНО ПРОШЛО ТЕСТЫ!!!!)
    # Раньше эту проверку пихал в try...
    if response.status_code != 200:
        logging.error(f'Ошибка API. Код ответа: {response.status_code}.')
        raise ApiError(f'Ошибка API. Код ответа: {response.status_code}.')
    
    logging.info(f'Получили ответ после GET-запроса по {ENDPOINT}, с параметрами: {payload}')
    return response.json()


def check_response(response):
    """Проверяет ответ API."""
    if not isinstance(response, dict):
        logging.error('Ответ API не является словарём.')
        raise TypeError
    if not isinstance(response.get(RESPONSE_KEYS[0]), list):    
        logging.error('Ответ в API не является списком.')
        raise TypeError
    for response_key in RESPONSE_KEYS:
        if response_key not in response:
            logging.error(f'Отсутствие ожидаемого ключа в ответе API - {response_key}')
            return False
    return True


def parse_status(homework):
    """Извлекает статус о конкретной домашней работе."""
    if 'homework_name' not in homework:
        logging.error('Отсутствует ключ "homework_name" в ответе API.')
        raise KeyError('Отсутствует ключ "homework_name" в ответе API.')
    homework_name = homework.get('homework_name')
    status = homework.get('status')
    if status not in HOMEWORK_VERDICTS:
        logging.error(f'Неожиданный статус домашней работы "{status}", обнаруженный в ответе API')
        raise ValueError(f'Неожиданный статус домашней работы "{status}", обнаруженный в ответе API.')
    verdict = HOMEWORK_VERDICTS.get(status)
    return f'Изменился статус проверки работы "{homework_name}". {verdict}'


def take_the_necessary_homework(response):
    """Функция для нахождения нужной домашней работы из списка."""
    for homework in response.get('homeworks'):
        if HOMEWORK_NAME in homework.get('homework_name'):
            return homework
    logging.debug(f'Работы - "{HOMEWORK_NAME}" - нет в ответе.')
    return None


def send_message(bot, message):
    """Отправление сообщения в Telegram-чат."""
    try:
        bot.send_message(TELEGRAM_CHAT_ID, message)
        logging.debug(f'Сообщение отправлено: "{message}"')
    except Exception as error:
        logging.error(f'Не удалось отправить сообщение в чат с ID {TELEGRAM_CHAT_ID}: {error}')


def main():
    """Основная логика работы бота."""
    # Проверяем доступность токенов.
    if not check_tokens():
        sys.exit()

    # Создаем объект класса бота
    bot = TeleBot(token=TELEGRAM_TOKEN)
    logging.info('Бот начал работу.')

    # Время в Unix 20 дней назад до запуска бота
    timestamp = int(time.time()) - SECONDS_IN_20_DAYS

    # Текущий статус
    status_of_homework = None

    while True:
        try:
            response = get_api_answer(timestamp)
            try:
                if not check_response(response):
                    send_message(bot, status_of_homework)
                    continue
            except TypeError:
                logging.error('Ошибка проверки ответа API. Продолжаем выполнение.')
                send_message(bot, status_of_homework)
                continue

            homework = take_the_necessary_homework(response)
            if homework is not None:
                try:
                    new_status = parse_status(homework)
                    if new_status != status_of_homework:
                        status_of_homework = new_status
                        send_message(bot, status_of_homework)
                        logging.debug(f'Новый статус - "{status_of_homework}"')
                    else:
                        logging.debug(f'Отсутствие в ответе новых статусов. Текущий - "{status_of_homework}".')
                except KeyError as error:
                    logging.error(f'Ошибка: {error}')
                    send_message(bot, 'Ошибка: отсутствует ключ "homework_name".')
                except Exception as error:
                    logging.error(f'Ошибка: {error}')
                    send_message(bot, f'Ошибка: {error}')

        except Exception as error:
            message = f'Сбой в работе программы: "{error}"'
            send_message(bot, message)
            sys.exit()
        finally:
            time.sleep(RETRY_PERIOD)

if __name__ == '__main__':
    main()
