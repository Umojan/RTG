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
