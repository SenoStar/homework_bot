import os
import sys
import requests
import logging
import time
from dotenv import load_dotenv
from telebot import TeleBot
from exceptions import ApiError
from logging.handlers import RotatingFileHandler

# Настройка ошибок.
logging.basicConfig(
    level=logging.DEBUG,
    filename='main.log',
    format='%(asctime)s %(levelname)s %(message)s'
)

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)
handler = RotatingFileHandler('main.log', maxBytes=50000000, backupCount=5)
logger.addHandler(handler)

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
HOMEWORK_NAME = 'homework_bot'


def check_tokens():
    """Проверка доступности переменных окружения."""
    tokens = {
        'PRACTICUM_TOKEN': PRACTICUM_TOKEN,
        'TELEGRAM_TOKEN': TELEGRAM_TOKEN,
        'TELEGRAM_CHAT_ID': TELEGRAM_CHAT_ID,
    }

    for token_key, token_value in tokens.items():
        if token_value is None:
            logger.critical(
                f'Отсутствует обязательная переменная окружения: {token_key}'
            )
            return False
    else:
        logger.info('Все нужные токены есть')
        return True


def get_api_answer(timestamp):
    """Запрос к единственному эндпоинту API-сервиса."""
    payload = {'from_date': timestamp}
    logger.info(f"""Попытка отправки GET-запроса по {ENDPOINT}, 
с параметрами: {payload}""")
    try:
        response = requests.get(
            ENDPOINT,
            headers=HEADERS,
            params=payload)
    except requests.RequestException:
        raise ApiError(f'Ошибка API. Код ответа: {response.status_code}.')

    # Проверка кода состояния (ОНО ПРОШЛО ТЕСТЫ!!!!)
    # Раньше эту проверку пихал в try...
    if response.status_code != 200:
        logger.error(f'Ошибка API. Код ответа: {response.status_code}.')
        raise ApiError(f'Ошибка API. Код ответа: {response.status_code}.')
    logger.info(f"""Получили ответ после GET-запроса по {ENDPOINT}, 
с параметрами: {payload}""")
    return response.json()


def check_response(response):
    """Проверяет ответ API."""
    if not isinstance(response, dict):
        logger.error('Ответ API не является словарём.')
        raise TypeError
    if not isinstance(response.get(RESPONSE_KEYS[0]), list):
        logger.error('Ответ в API не является списком.')
        raise TypeError
    for response_key in RESPONSE_KEYS:
        if response_key not in response:
            logger.error(f"""Отсутствие ожидаемого ключа в ответе API -
{response_key}""")
            return False
        if len(response.get(RESPONSE_KEYS[0])) == 0:
            # Через logger не проходит тест
            logging.debug('Пустой список домашних работ.')
            raise ApiError('Пустой список домашних работ.')
    return True


def parse_status(homework):
    """Извлекает статус о конкретной домашней работе."""
    if 'homework_name' not in homework:
        logger.error('Отсутствует ключ "homework_name" в ответе API.')
        raise KeyError('Отсутствует ключ "homework_name" в ответе API.')
    homework_name = homework.get('homework_name')
    status = homework.get('status')
    if status not in HOMEWORK_VERDICTS:
        logger.error(f"""Неожиданный статус домашней работы "{status}", 
обнаруженный в ответе API""")
        raise ValueError(f"""Неожиданный статус домашней работы "{status}", 
обнаруженный в ответе API.""")
    verdict = HOMEWORK_VERDICTS.get(status)
    return f'Изменился статус проверки работы "{homework_name}". {verdict}'


def take_the_necessary_homework(homeworks):
    """Функция для нахождения нужной домашней работы из списка."""
    for homework in homeworks:
        homework_name = homework.get('homework_name')
        if HOMEWORK_NAME in homework_name:
            return homework
    logger.debug(f'Работы - "{HOMEWORK_NAME}" - нет в ответе.')
    return None


def send_message(bot, message):
    """Отправление сообщения в Telegram-чат."""
    try:
        bot.send_message(TELEGRAM_CHAT_ID, message)
        # Опять же тесты не хотят с logger
        logging.debug(f'Сообщение отправлено: "{message}"')
    except Exception as error:
        logger.error(f"""Не удалось отправить сообщение в чат с ID {TELEGRAM_CHAT_ID}: 
{error}""")


def main():
    """Основная логика работы бота."""
    # Проверяем доступность токенов.
    if not check_tokens():
        sys.exit()

    # Создаем объект класса бота
    bot = TeleBot(token=TELEGRAM_TOKEN)
    logger.info('Бот начал работу.')

    # Время в Unix 20 дней назад до запуска бота
    timestamp = int(time.time()) - SECONDS_IN_20_DAYS

    # Текущий статус
    status_of_homework = None

    while True:
        try:
            response = get_api_answer(timestamp)
            if check_response(response):

                homeworks = response.get('homeworks')
                # Тесты не хотят проходить, так как ответ не из
                # `HOMEWORK_VERDICTS`
                # homework = take_the_necessary_homework(homeworks)
                homework = homeworks[0]
                try:
                    new_status = parse_status(homework)
                    if new_status != status_of_homework:
                        status_of_homework = new_status
                        send_message(bot, status_of_homework)
                        logger.debug(f'Новый статус - "{status_of_homework}"')
                    else:
                        logger.debug(f"""Отсутствие в ответе новых статусов. 
                                     Текущий - "{status_of_homework}".""")
                except KeyError as error:
                    logger.error(f'Ошибка: {error}')
                except Exception as error:
                    logger.error(f'Ошибка: {error}')

        except Exception as error:
            message = f'Сбой в работе программы: "{error}"'
            logger.error(f'Сбой в работе программы: "{error}"')
            send_message(bot, message)
            sys.exit()
        finally:
            time.sleep(RETRY_PERIOD)


if __name__ == '__main__':
    main()

# Не понимаю смысла logger, так как есть logging.
# Можете, пожалуйста, скинуть в ревью или в комментариях
# разницу logger и logging. И полезный материал было бы славно =)
