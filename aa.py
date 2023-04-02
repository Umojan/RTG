# coding=utf-8
from config_data.config import BOT_TOKEN

import telebot
from telebot import types
from telegram_bot_calendar import WYearTelegramCalendar, LSTEP

from api_handlers.api_functions import city_finder, tickets_finder

from loguru import logger
import json
import datetime

# coding=utf-8
from peewee import *
from loguru import logger

db = SqliteDatabase('database.db')


class BaseModel(Model):
    class Meta:
        database = db


class UserData(BaseModel):
    user_id = IntegerField(null=True)
    first_name = CharField(null=True)
    last_name = CharField(null=True)
    sort_by = CharField(null=True)
    user_step = CharField(null=True)
    origin = CharField(null=True)
    origin_code = CharField(null=True)
    destination = CharField(null=True)
    destination_code = CharField(null=True)
    date = DateField(null=True)
    adults = IntegerField(null=True)
    children = IntegerField(null=True)
    infants = IntegerField(null=True)
    flight_class = CharField(null=True)
    msg_menu_id = IntegerField(null=True)
    current_msg_id = IntegerField(null=True)
    history = CharField(null=True)


db.connect()
db.create_tables([UserData])


class User:
    def __init__(self, user_id):
        self.user_id = user_id
        UserData.get_or_create(user_id=user_id)

    def add(self, **kwargs):
        user, created = UserData.get_or_create(user_id=self.user_id)
        for key, value in kwargs.items():
            if hasattr(UserData, key):
                setattr(user, key, value)
        user.save()

    def get(self):
        user = UserData.get(UserData.user_id == self.user_id)
        return {
            "user_id": user.user_id,
            "first_name": user.first_name,
            "last_name": user.last_name,
            "sort_by": user.sort_by,
            "user_step": user.user_step,
            "origin": user.origin,
            "origin_code": user.origin_code,
            "destination": user.destination,
            "destination_code": user.destination_code,
            "date": user.date,
            "adults": user.adults,
            "children": user.children,
            "infants": user.infants,
            "flight_class": user.flight_class,
            "msg_menu_id": user.msg_menu_id,
            "current_msg_id": user.current_msg_id,
            "history": user.history,
        }

    def delete(self):
        user = UserData.get(UserData.user_id == self.user_id)
        user.delete_instance()


def check_user_exists(user_id):
    return UserData.select().where(UserData.user_id == user_id).exists()
'''
usage example:

user = User(1234)
user.add(last_name='Loe')
user_data = user.get()
'''

# coding=utf-8
import datetime
import math

from config_data import config
from loader import logger
import requests

headers = {
    "X-RapidAPI-Key": config.API_KEY,
    "X-RapidAPI-Host": "travel-advisor.p.rapidapi.com"
}


@logger.catch()
def api_request(method_endswith, params, method_type):
    url = f"https://travel-advisor.p.rapidapi.com/{method_endswith}"

    if method_type == 'GET':
        return get_request(url=url, params=params)
    # else:
    # return post_request(url=url, params=params)


@logger.catch()
def get_request(url, params):
    try:
        response = requests.request('GET', url, headers=headers, params=params, timeout=10)
        if response.status_code == requests.codes.ok:
            return True, response
        elif response.status_code == 429:
            logger.error('API service subscription expired')
            return False, 'Произошла непредвиденная ошибка'
        else:
            logger.error('Other request error')
            return False, 'Произошла непредвиденная ошибка'
    except:
        return False, 'Нет ответа от сервера'


@logger.catch()
def city_finder(city):
    if len(city) <= 2:
        return False, 'Название города слишком короткое'

    status, response = api_request(method_endswith="airports/search",
                                   params={"query": city, "locale": "ru_RU"},
                                   method_type='GET')
    if status:
        if len(response.json()):
            cities = []
            display_titles = []
            for city in response.json():
                if 'display_name' in city and city['display_name'] not in display_titles:
                    cities.append(
                        {'city_code': city['code'],
                         'city_name': city['city_name'],
                         'display_name': city['display_name']}
                    )
                    display_titles.append(city['display_name'])
            return True, cities
        else:
            return False, 'Город не найден'
    else:
        return False, response


def tickets_finder(user_data):
    def local_time(world_time, city):
        timestamp = datetime.datetime.fromisoformat(world_time)
        timezone = datetime.timezone(datetime.timedelta(hours=6), city)
        local_time = timestamp.astimezone(timezone)

        return local_time.strftime("%Y-%m-%d %H:%M:%S")

    def travel_time(time1, time2):
        dt1 = datetime.datetime.fromisoformat(time1)
        dt2 = datetime.datetime.fromisoformat(time2)

        return dt2 - dt1

    def handle_errors(error_result):
        if 'error' in error_result:
            if error_result['error']['t'] == 'GENERIC':
                error_reply = f'Мы не нашли никаких рейсов между {origin} и {destination}. ' \
                                 f'Попробуйте выбрать соседний аэропорт или другие даты поездки.'

            elif error_result['error']['t'] == 'SEARCH_FAILURE':
                error_reply = 'Наш сервер сейчас перегружен, пожалуйста, подождите несколько минут и повторите попытку.'

            elif error_result['error']['t'] == 'CLASS_OF_SERVICE_UNAVAILABLE':
                if flight_class == 1:
                    flight_class_name = 'бизнес-'
                elif flight_class == 2:
                    flight_class_name = 'первого '
                else:
                    flight_class_name = 'эконом '
                error_reply = f'Билеты {flight_class_name}класса не найдены для вашего поиска.'
            else:
                error_reply = error_result['error']['m']

            logger.warning(f"Error in API: {error_result['error']['t']}")
            return True, error_reply
        else:
            return False, 'OK'

    logger.info(f"API: Creating a session")
    origin = user_data['origin']
    destination = user_data['destination']
    origin_code = user_data['origin_code']
    destination_code = user_data['destination_code']
    date = user_data['date'].strftime("%Y-%m-%d")
    adults = user_data['adults']
    children = user_data['children']
    str_children = ','.join([str(11) for i in range(children)])
    flight_class = user_data['flight_class']
    sort_by = user_data['sort_by']

    # ---------- create session ----------
    params = {"o1": origin_code, "d1": destination_code, "dd1": date, "currency": "USD", "ta": adults,
              "tc": str_children, "c": flight_class}
    status, response = api_request(method_endswith="flights/create-session",
                                   params=params,
                                   method_type='GET')

    if status is False:
        return False, response
    result = response.json()

    # проверка на наличие ошибок
    status, error_response = handle_errors(result)
    if status:
        return False, error_response

    sid = result['search_params']['sid']
    # ------------------------------------
    logger.info(f"API: Creating a poll")
    # --------------- poll ---------------
    repeats = 5
    for i in range(1, repeats + 1):
        params = {"sid": sid, "so": sort_by, "currency": "USD", "n": "15",
                  "ns": "NON_STOP,ONE_STOP,TWO_PLUS", "o": "0"}
        status, response = api_request(method_endswith="flights/poll",
                                       params=params,
                                       method_type='GET')

        if status is False:
            return False, response
        result = response.json()

        # проверка на наличие ошибок
        status, error_response = handle_errors(result)
        if status:
            return False, error_response


        try:
            if result['itineraries'][0]['impressionId']:
                break
        except:
            logger.warning(f"API: [impressionId] not found ({i})")
            if i == repeats:
                return False, 'Возникла ошибка, попробуйте еще раз.'

    # ------------------------------------
    logger.info(f"API: Creating a list of flights")
    # --------- list of flights ----------
    search_hash = result['summary']['sh']
    search_result = []
    for i_city in result['itineraries']:
        impression_id = i_city['l'][0]['impressionId']

        flight_id = i_city['l'][0]['id']

        price = i_city['l'][0]['pr']['p']
        departure_date = i_city['f'][0]['l'][0]['dd']
        arrival_date = i_city['f'][0]['l'][0]['ad']
        airplane = i_city['f'][0]['l'][0]['e']

        # -------------- get url -------------
        params = {"searchHash": search_hash, "Dest": destination_code, "id": flight_id, "Orig": origin_code,
                  "searchId": sid, "impressionId": impression_id}
        status, response = api_request(method_endswith="flights/get-booking-url",
                                       params=params,
                                       method_type='GET')

        if status is False:
            return False, response
        result = response.json()

        url = result["partner_url"]
        # ------------------------------------

        ticket_info = {
            'price': math.ceil(price),
            'total_price': math.ceil(price * (adults + children)),
            'departure_date': local_time(departure_date, origin_code),
            'arrival_date': local_time(arrival_date, destination_code),
            'flight_time': travel_time(departure_date, arrival_date),
            'airplane': airplane,
            'url': url
        }
        search_result.append(ticket_info)

    return True, search_result



bot = telebot.TeleBot(BOT_TOKEN)

logger.add(
    'logs/logs.log',
    level='DEBUG',
    format="{time} | {level} | {name}:{function}:{line}  |  {message}    {exception}"
)


# -------------- start ---------------
@logger.catch
@bot.message_handler(commands=['start'])
def start(message):
    if check_user_exists(message.chat.id):
        bot.send_message(message.chat.id, f'C возвращением *{message.from_user.first_name}*!\n\n'
                                          'Вызовите /menu чтобы ввести критерии поиска или '
                                          '/help для помощи в управлении ботом', parse_mode="Markdown")
        logger.info(f'/start (EXITING user)', extra={'user_id': message.chat.id})
    else:
        bot.send_message(message.chat.id, f'Привет, *{message.from_user.first_name}*! Я бот для поиска авиабилетов!\n\n'
                                          'Вызовите /menu чтобы ввести критерии поиска или '
                                          '/help для помощи в управлении ботом', parse_mode="Markdown")
        logger.info(f'/start (NEW user)')
    # добавление пользователя в базу данных
    User(message.chat.id).add(
        first_name=message.from_user.first_name,
        last_name=message.from_user.last_name,
        flight_class='0',
        sort_by='PRICE',
        adults=1, children=0, infants=0
    )

    menu(message)


# --------------- menu ---------------
@logger.catch
@bot.message_handler(commands=['menu'])
def menu(message):
    logger.info(f'Menu')

    user = User(message.chat.id)

    markup = types.InlineKeyboardMarkup(row_width=3)
    button_origin = types.InlineKeyboardButton(text=menu_btn_text(message, 'origin'),
                                               callback_data='menu_origin')
    button_destination = types.InlineKeyboardButton(text=menu_btn_text(message, 'destination'),
                                                    callback_data='menu_destination')
    button_date = types.InlineKeyboardButton(text=menu_btn_text(message, 'date'), callback_data='menu_date')
    button_passengers = types.InlineKeyboardButton(text=menu_btn_text(message, 'passengers'),
                                                   callback_data='menu_passengers')
    button_flight_class = types.InlineKeyboardButton(text=menu_btn_text(message, 'flight_class'),
                                                     callback_data='menu_flight_class')
    button_sort_by = types.InlineKeyboardButton(text=menu_btn_text(message, 'sort_by'),
                                                callback_data='menu_sort_by')
    btn_search = types.InlineKeyboardButton(text='-   Поиск   -', callback_data='menu_search')

    markup.add(button_origin)
    markup.add(button_destination)
    markup.add(button_date)
    markup.add(button_passengers, button_flight_class)
    markup.add(button_sort_by)
    markup.add(btn_search)

    # удаление current_msg_id
    current_msg_id = user.get()['current_msg_id']
    if current_msg_id:
        try:
            bot.delete_message(chat_id=message.chat.id, message_id=current_msg_id)
        except telebot.apihelper.ApiTelegramException:
            pass
    # удаление предыдущего menu
    old_msg_id = user.get()['msg_menu_id']
    user.add(msg_menu_id=bot.send_message(message.chat.id, 'Выберите опцию:                                 -',
                                          reply_markup=markup).message_id)

    try:
        bot.delete_message(chat_id=message.chat.id, message_id=old_msg_id)
    except telebot.apihelper.ApiTelegramException:
        pass

    user.add(user_step=None)


@logger.catch()
def menu_btn_text(message, button_name):
    def date_to_str(date):
        months = ["января", "февраля", "марта", "апреля", "мая", "июня",
                  "июля", "августа", "сентября", "октября", "ноября", "декабря"]
        return f"{date.day} {months[date.month - 1]}"

    user_data = User(message.chat.id).get()

    if button_name == 'origin':
        if user_data['origin'] is None:
            return 'Откуда'
        else:
            return f"{user_data['origin']} ({user_data['origin_code']})"

    elif button_name == 'destination':
        if user_data['destination'] is None:
            return 'Куда'
        else:
            return f"{user_data['destination']} ({user_data['destination_code']})"

    elif button_name == 'date':
        if user_data['date'] is None:
            return 'Дата'
        else:
            return date_to_str(user_data['date'])

    elif button_name == 'passengers':
        adults = user_data['adults']
        children = user_data['children']
        infants = user_data['infants']
        count = adults + children + infants
        if count % 10 == 1 and count % 100 != 11:
            return f"{count} пассажир"
        elif count % 10 in [2, 3, 4] and count % 100 not in [12, 13, 14]:
            return f"{count} пассажира"
        else:
            return f"{count} пассажиров"

    elif button_name == 'flight_class':
        if user_data["flight_class"] == '0':
            return 'Эконом класс'
        elif user_data["flight_class"] == '1':
            return 'Бизнес класс'
        elif user_data["flight_class"] == '2':
            return 'Первый класс'

    elif button_name == 'sort_by':
        if user_data["sort_by"] == 'PRICE':
            return f'Сортировать по цене'
        elif user_data["sort_by"] == 'ML_BEST_VALUE':
            return f'Сортировать по лучшему предложению'
        elif user_data["sort_by"] == 'LATEST_OUTBOUND_DEPARTURE':
            return f'Сортировать по времени вылета'


# ----------- menu handler -----------
@logger.catch
@bot.callback_query_handler(func=lambda call: call.data.startswith('menu'))
def menu_handler(call):
    user = User(call.message.chat.id)
    user_data = user.get()
    # удаление current_msg_id
    current_msg_id = user_data['current_msg_id']
    if current_msg_id:
        try:
            bot.delete_message(chat_id=call.message.chat.id, message_id=current_msg_id)
        except telebot.apihelper.ApiTelegramException:
            pass

    if call.data == 'menu_origin':
        step = 'origin'
        user.add(user_step=step)
        logger.info(f"Step: {step}")
        bot.send_message(call.message.chat.id, 'Откуда вы летите?')
    elif call.data == 'menu_destination':
        step = 'destination'
        user.add(user_step=step)
        logger.info(f"Step: {step}")
        bot.send_message(call.message.chat.id, 'Куда вы летите?')

    elif call.data == 'menu_date':
        step = 'date'
        user.add(user_step=step)
        logger.info(f"Step: {step}")
        calendar_starter(message=call.message)

    elif call.data == 'menu_passengers':
        step = 'passengers'
        user.add(user_step=step)
        logger.info(f"Step: {step}")
        passengers_starter(message=call.message)

    elif call.data == 'menu_flight_class':
        step = 'flight_class'
        user.add(user_step=step)
        logger.info(f"Step: {step}")
        flight_class_starter(message=call.message)

    elif call.data == 'menu_sort_by':
        step = 'sort_by'
        user.add(user_step=step)
        logger.info(f"Step: {step}")
        sort_by_starter(message=call.message)

    elif call.data == 'menu_search':
        step = 'search'
        user.add(user_step=step)
        logger.info(f"Step: {step}")
        ticket_search(message=call.message)


# --------------- help ---------------
@logger.catch()
@bot.message_handler(commands=['help'])
def help_command(message):
    help_text = '''
Для начала работы вызовите /start, затем в появившемся меню заполните все поля, после чего выполните поиск.\n
Для просмотра истории вызовите /history.

Если вы случайно удалили сообщение, то просто вызовите /menu для повторной отправки.
    '''

    bot.send_message(message.chat.id, help_text)


# ------------- history --------------
@logger.catch()
@bot.message_handler(commands=['history'])
def history_get(message):
    user = User(message.chat.id)
    user_data = user.get()
    if user_data['history']:
        history_data = json.loads(user_data['history'])
        logger.info(f'Getting ticket search history ({len(history_data)} items)')

        tick_search_num = 0
        for tick_search in history_data:
            markup = types.InlineKeyboardMarkup()
            markup.add(types.InlineKeyboardButton(text='Поиск', callback_data=f'history_{tick_search_num}'))

            flight_class = ''
            if tick_search["flight_class"] == '0':
                flight_class = 'Эконом класс'
            elif tick_search["flight_class"] == '1':
                flight_class = 'Бизнес класс'
            elif tick_search["flight_class"] == '2':
                flight_class = 'Первый класс'

            text = f"        {tick_search['search_time']}\n\n" \
                   f"Откуда: {tick_search['origin']}\n" \
                   f'Куда: {tick_search["destination"]}\n' \
                   f"Дата вылета: {tick_search['date']}\n\n" \
                   f" Кол-во взрослых: {tick_search['adults']}\n" \
                   f" Кол-во детей: {tick_search['children']}\n" \
                   f" Кол-во младенцев: {tick_search['infants']}\n\n" \
                   f" {flight_class}" \

            bot.send_message(message.chat.id, text, reply_markup=markup)

            tick_search_num += 1
    else:
        bot.send_message(message.chat.id, 'Кажется вы еще не искали авиабилеты')


@logger.catch()
@bot.callback_query_handler(func=lambda call: call.data.startswith('history'))
def history_get_handler(call):
    logger.info(f"Adding user data from the history to the database")
    user = User(call.message.chat.id)
    user_data = user.get()

    history_data = json.loads(user_data['history'])
    tick_search = history_data[int(call.data[-1:])]

    user.add(
        origin=tick_search['origin'],
        origin_code=tick_search['origin_code'],
        destination=tick_search['destination'],
        destination_code=tick_search['destination_code'],
        date=tick_search['date'],
        adults=tick_search['adults'],
        children=tick_search['children'],
        infants=tick_search['infants'],
        flight_class=tick_search['flight_class'],
        sort_by=tick_search['sort_by']
    )

    menu(call.message)


@logger.catch()
def history_add(message):
    logger.info(f'Adding a ticket search to history')
    user = User(message.chat.id)
    user_data = user.get()

    search_time = datetime.datetime.now().strftime("%d:%m:%Y %H:%m")

    tick_search = {'search_time': search_time,
                   'origin': user_data['origin'],
                   'origin_code': user_data['origin_code'],
                   'destination': user_data['destination'],
                   'destination_code': user_data['destination_code'],
                   'date': user_data['date'],
                   'adults': user_data['adults'],
                   'children': user_data['children'],
                   'infants': user_data['infants'],
                   'flight_class': user_data['flight_class'],
                   'sort_by': user_data['sort_by']}
    if user_data['history']:
        history_data = json.loads(user_data['history'])
        if len(history_data) > 10:
            history_data.pop(0)
    else:
        history_data = []
    history_data.append(tick_search)
    user.add(history=json.dumps(history_data, indent=4, sort_keys=True, default=str))


# --------------- city ---------------
@logger.catch()
@bot.message_handler(content_types=['text'])
def city_starter(message):
    logger.info(f"City search")
    user = User(message.chat.id)
    if user.get()["user_step"] in ('origin', 'destination'):
        status, response = city_finder(message.text)

        if status:
            markup = types.InlineKeyboardMarkup()
            for i_city in response:
                markup.add(telebot.types.InlineKeyboardButton(
                    i_city['display_name'],
                    callback_data=f"city/{i_city['city_code']}/{i_city['city_name']}")
                )

            user.add(current_msg_id=bot.send_message(message.chat.id,
                                                     f"Уточните, пожалуйста:",
                                                     reply_markup=markup).message_id)
        else:
            bot.send_message(message.chat.id, response)


@logger.catch()
@bot.callback_query_handler(func=lambda call: call.data.startswith('city'))
def city_handler(call):
    user = User(call.message.chat.id)
    user_data = user.get()
    city_list = call.data.split("/")
    city_code = city_list[1]
    city_name = city_list[2]

    if user_data['user_step'] == 'origin':
        user.add(origin=city_name, origin_code=city_code)
    elif user_data['user_step'] == 'destination':
        user.add(destination=city_name, destination_code=city_code)

    menu(call.message)


# ------------- calendar -------------
@logger.catch()
@bot.message_handler(func=lambda x: User(bot.user.id).get()["user_step"] == 'date')
def calendar_starter(message):
    logger.info(f"Selecting a date")
    user = User(message.chat.id)
    calendar, step = WYearTelegramCalendar(min_date=datetime.date.today(), locale='ru').build()

    user.add(current_msg_id=bot.send_message(message.chat.id,
                                             f"Выберите {ru_step(LSTEP[step])}",
                                             reply_markup=calendar).message_id)


@logger.catch()
@bot.callback_query_handler(func=WYearTelegramCalendar.func())
def calendar_handler(call):
    user = User(call.message.chat.id)
    result, key, step = WYearTelegramCalendar(min_date=datetime.date.today(), locale='ru').process(call.data)
    if not result and key:
        bot.edit_message_text(f"Выберите {ru_step(LSTEP[step])}",
                              call.message.chat.id,
                              call.message.message_id,
                              reply_markup=key)
    elif result:
        user.add(date=result)
        bot.edit_message_text(f"Дата вылета {result}",
                              call.message.chat.id,
                              call.message.message_id)
        user.add(current_msg_id=None)
        menu(call.message)


def ru_step(step):
    if step == 'year':
        return 'год'
    elif step == 'month':
        return 'месяц'
    elif step == 'day':
        return 'день'


# ------------ passengers ------------
@logger.catch()
def passengers_markup(message):
    user = User(message.chat.id)
    # Установка кнопок
    markup = types.InlineKeyboardMarkup(row_width=3)

    # Первый блок кнопок: взрослые
    name_button = telebot.types.InlineKeyboardButton("Взрослые (старше 12 лет)", callback_data="passengers_adults_name")
    count_button = telebot.types.InlineKeyboardButton(f"{user.get()['adults']}",
                                                      callback_data="passengers_adults_count")
    left_arrow = telebot.types.InlineKeyboardButton(passengers_btn_text(message, 'adults-'),
                                                    callback_data="passengers_adults-")
    right_arrow = telebot.types.InlineKeyboardButton(passengers_btn_text(message, 'adults+'),
                                                     callback_data="passengers_adults+")
    markup.add(name_button)
    markup.add(left_arrow, count_button, right_arrow)

    # Второй блок кнопок: дети
    name_button = telebot.types.InlineKeyboardButton("Дети (от 2 до 12 лет)", callback_data="passengers_children_name")
    count_button = telebot.types.InlineKeyboardButton(f"{user.get()['children']}",
                                                      callback_data="passengers_children_count")
    left_arrow = telebot.types.InlineKeyboardButton(passengers_btn_text(message, 'children-'),
                                                    callback_data="passengers_children-")
    right_arrow = telebot.types.InlineKeyboardButton(passengers_btn_text(message, 'children+'),
                                                     callback_data="passengers_children+")
    markup.add(name_button)
    markup.add(left_arrow, count_button, right_arrow)

    # Третий блок кнопок: младенцы
    name_button = telebot.types.InlineKeyboardButton(f"Младенцы (до 2 лет, без места)",
                                                     callback_data="passengers_infants_name")
    count_button = telebot.types.InlineKeyboardButton(f"{user.get()['infants']}",
                                                      callback_data="passengers_infants_count")
    left_arrow = telebot.types.InlineKeyboardButton(passengers_btn_text(message, 'infants-'),
                                                    callback_data="passengers_infants-")
    right_arrow = telebot.types.InlineKeyboardButton(passengers_btn_text(message, 'infants+'),
                                                     callback_data="passengers_infants+")
    markup.add(name_button)
    markup.add(left_arrow, count_button, right_arrow)

    # Четвертый блок кнопок: готово
    done_button = telebot.types.InlineKeyboardButton("Готово", callback_data="passengers_done")
    markup.add(done_button)

    return markup


@logger.catch()
@bot.message_handler(func=lambda x: User(bot.user.id).get()["user_step"] == 'passengers')
def passengers_starter(message):
    logger.info(f"Selecting the number of passengers")
    user = User(message.chat.id)
    user.add(current_msg_id=bot.send_message(message.chat.id, 'Укажите количество пассажиров',
                                             reply_markup=passengers_markup(message)).message_id)


@logger.catch()
@bot.callback_query_handler(func=lambda call: call.data.startswith('passengers'))
def passengers_handler(call):
    user = User(call.message.chat.id)
    user_data = user.get()

    adults = user_data['adults']
    children = user_data['children']
    infants = user_data['infants']
    passengers_sum = adults + children + infants

    msg_different = False

    if call.data == 'passengers_adults-':
        if adults > 1 and adults > infants:
            user.add(adults=adults - 1)
            msg_different = True
    elif call.data == 'passengers_adults+':
        if passengers_sum < 9:
            user.add(adults=adults + 1)
            msg_different = True
        else:
            bot.send_message(call.message.chat.id, 'Может быть не больше 9 пассажиров')

    elif call.data == 'passengers_children-':
        if children > 0:
            user.add(children=children - 1)
            msg_different = True
    elif call.data == 'passengers_children+':
        if passengers_sum < 9:
            user.add(children=children + 1)
            msg_different = True
        else:
            bot.send_message(call.message.chat.id, 'Может быть не больше 9 пассажиров')

    elif call.data == 'passengers_infants-':
        if infants > 0:
            user.add(infants=infants - 1)
            msg_different = True
    elif call.data == 'passengers_infants+':
        if passengers_sum < 9 and infants < adults:
            user.add(infants=infants + 1)
            msg_different = True
        elif passengers_sum == 9:
            bot.send_message(call.message.chat.id, 'Может быть не более 9 пассажиров')
        elif infants == adults:
            bot.send_message(call.message.chat.id, 'Не более одного младенца на одного взрослого')

    if call.data == 'passengers_done':
        bot.edit_message_text(f"Взрослых:  {adults}\n"
                              f"Детей:     {children}\n"
                              f"Младенцев: {infants}",
                              call.message.chat.id,
                              user.get()['current_msg_id'])

        user.add(current_msg_id=None)
        menu(call.message)
    elif msg_different:
        bot.edit_message_text('Укажите количество пассажиров',
                              call.message.chat.id,
                              user.get()['current_msg_id'],
                              reply_markup=passengers_markup(call.message))


@logger.catch()
def passengers_btn_text(message, button_name):
    user = User(message.chat.id)
    user_data = user.get()

    adults = user_data['adults']
    children = user_data['children']
    infants = user_data['infants']
    passengers_sum = adults + children + infants

    if button_name == 'adults-':
        if adults > 1 and adults > infants:
            return '-'
        else:
            return ' '
    elif button_name == 'adults+':
        if passengers_sum < 9:
            return '+'
        else:
            return ' '

    elif button_name == 'children-':
        if children > 0:
            return '-'
        else:
            return ' '
    elif button_name == 'children+':
        if passengers_sum < 9:
            return '+'
        else:
            return ' '

    elif button_name == 'infants-':
        if infants > 0:
            return '-'
        else:
            return ' '
    elif button_name == 'infants+':
        if infants < adults and passengers_sum < 9:
            return '+'
        else:
            return ' '


# ----------- flight class -----------
@logger.catch()
def flight_class_starter(message):
    logger.info(f"Selecting a flight class")
    user = User(message.chat.id)
    markup = types.InlineKeyboardMarkup(row_width=3)

    economy_button = telebot.types.InlineKeyboardButton("Эконом класс",
                                                        callback_data="class_economy")
    business_button = telebot.types.InlineKeyboardButton("Бизнес класс",
                                                         callback_data="class_business")
    first_button = telebot.types.InlineKeyboardButton("Первый класс",
                                                      callback_data="class_first")
    markup.add(economy_button)
    markup.add(business_button)
    markup.add(first_button)

    user.add(current_msg_id=bot.send_message(message.chat.id, 'Выберите класс полета',
                                             reply_markup=markup).message_id)


@logger.catch()
@bot.callback_query_handler(func=lambda call: call.data.startswith('class'))
def flight_class_handler(call):
    user = User(call.message.chat.id)

    if call.data == 'class_economy':
        user.add(flight_class='0')
    elif call.data == 'class_business':
        user.add(flight_class='1')
    elif call.data == 'class_first':
        user.add(flight_class='2')

    menu(call.message)


# ------------- sort_by --------------
@logger.catch()
@bot.message_handler(func=lambda x: User(bot.user.id).get()["user_step"] == 'sort_by')
def sort_by_starter(message):
    logger.info(f"Selecting the sorting type")
    user = User(message.chat.id)
    markup = types.InlineKeyboardMarkup(row_width=3)

    economy_button = telebot.types.InlineKeyboardButton("Цена",
                                                        callback_data="sort_by_price")
    business_button = telebot.types.InlineKeyboardButton("Лучшее предложение",
                                                         callback_data="sort_by_best_value")
    first_button = telebot.types.InlineKeyboardButton("Время вылета",
                                                      callback_data="sort_by_time")
    markup.add(economy_button)
    markup.add(business_button)
    markup.add(first_button)

    user.add(current_msg_id=bot.send_message(message.chat.id, 'Выберите способ сортировки билетов',
                                             reply_markup=markup).message_id)


@logger.catch()
@bot.callback_query_handler(func=lambda call: call.data.startswith('sort_by'))
def sort_by_handler(call):
    user = User(call.message.chat.id)

    if call.data == 'sort_by_price':
        user.add(sort_by='PRICE')
    elif call.data == 'sort_by_best_value':
        user.add(sort_by='ML_BEST_VALUE')
    elif call.data == 'sort_by_time':
        user.add(sort_by='LATEST_OUTBOUND_DEPARTURE')

    menu(call.message)


# -------------- search --------------
@logger.catch()
def ticket_search(message):
    logger.info(f"Starting the ticket search")
    user = User(message.chat.id)
    user_data = user.get()
    # проверка данных
    if all((user_data['origin'], user_data['destination'], user_data['date'])):
        # удаление menu
        old_msg_id = user.get()['msg_menu_id']
        try:
            bot.delete_message(chat_id=message.chat.id, message_id=old_msg_id)
        except telebot.apihelper.ApiTelegramException:
            pass

        # отправка сообщения загрузки
        user.add(current_msg_id=bot.send_message(message.chat.id, '⌛️').message_id)

        # отправка API запроса
        status, response = tickets_finder(user_data)

        # удаление сообщения загрузки
        current_msg_id = user.get()['current_msg_id']
        if current_msg_id:
            try:
                bot.delete_message(chat_id=message.chat.id, message_id=current_msg_id)
            except telebot.apihelper.ApiTelegramException:
                pass

        if status:
            logger.info(f"Sending ticket messages")
            for ticket in response:
                markup = types.InlineKeyboardMarkup()
                markup.add(types.InlineKeyboardButton("Купить", url=ticket['url']))
                bot.send_message(message.chat.id,
                                 f"{user_data['origin']} - {user_data['destination']}\n\n"
                                 f"Цена за человека: {ticket['price']}\n"
                                 f"Итого:            {ticket['total_price']}\n\n"
                                 f"Время вылета:     {ticket['departure_date']}\n"
                                 f"Время прилета:    {ticket['arrival_date']}\n"
                                 f"Время в полете:   {ticket['flight_time']}\n\n"
                                 f"Самолет:          {ticket['airplane']}",
                                 reply_markup=markup)

            # добавление данных в историю
            history_add(message)
        else:
            logger.info(f"Search error: {response}")
            bot.send_message(message.chat.id, response)

        menu(message)
    else:
        bot.send_message(message.chat.id, 'Укажите все значения в форме')


bot.polling()
