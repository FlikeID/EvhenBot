# -*- coding: utf-8 -*-
import random
from difflib import SequenceMatcher
import argparse
import requests
import json

DEBUG = True
print("Старт бота")
parser = argparse.ArgumentParser(description='Главный процесс бота')
parser.add_argument("--token", required=True, type=str, help="Токен бота")
args = parser.parse_args()
TOKEN = args.token
print("Стартанули")
class Actions:

    def __init__(self, debug=False):
        self.debug = debug

    def compare_text(self, text_1, text_2: list, accuracy=0.75):
        for items in text_2:
            precision = SequenceMatcher(lambda x: x == " ", text_1.lower(), items.lower()).ratio()
            if self.debug:
                print(r"Debug | CompareT: ", precision, "/", accuracy, '\t\t', text_1, ' |', items, sep="")
            if precision >= accuracy:
                return True
        return False

    def compare_word(self, text_1, text_2: list, accuracy=0.75):
        for word in text_1.split():
            for items in text_2:
                precision = SequenceMatcher(lambda x: x == " ", word.lower(), items.lower()).ratio()
                if self.debug:
                    print(r"Debug | CompareW: ", precision, "/", accuracy, '\t\t', word, ' |', items, sep="")
                if precision >= accuracy:
                    return True
        return False

    def compare_first_word(self, text_1, text_2: list, accuracy=0.75):
        if len(text_1) > 0:
            word = text_1.split()[0]
        else:
            if self.debug:
                print(r"Debug | CompareF: Haven't any word")
            return False
        for items in text_2:
            precision = SequenceMatcher(lambda x: x == " ", word.lower(), items.lower()).ratio()
            if self.debug:
                print(r"Debug | CompareF: ", precision, "/", accuracy, '\t\t', word, ' |', items, sep="")
            if precision >= accuracy:
                return True
        return False


class ExceptionTGMSG(Exception):

    def __init__(self, message, errors):
        super().__init__(message)
        self.errors = f'TG_MSG_Exception[{errors}]'
        self.code = 'errors'


class TGBot:

    def __init__(self, token, debug=False):

        self.debug = debug
        self.token = token
        self.update_id = None
        me = self.method('getMe')
        self.id = me['id']
        self.nick = me['username']

    def method(self, name, raw=False, **kwargs, ):

        params = ''
        for param in kwargs:
            params += f'{param}={kwargs[param]}&'
        response = requests.get(f'https://api.telegram.org/bot{self.token}/{name}?{params}')
        response_json = json.loads(response.text)

        if not response_json['ok']:
            if self.debug:
                print(r"Debug | Method: ", name, response_json)
            raise ExceptionTGMSG(response_json['description'],
                                 response_json['error_code'])
        if raw:
            return response_json
        return response_json["result"]

    def set_update_id(self, response):

        if len(response) > 0:
            # если массив не пустой, получить апдейт id последенего действия плюс единица
            self.update_id = response[len(response) - 1]["update_id"] + 1

    def get_pool(self):
        if self.update_id is None:
            response = self.method(name='getUpdates')
        else:
            response = self.method(name='getUpdates', offset=self.update_id)

        self.set_update_id(response)

        if self.debug:
            if len(response)>0:
                print(r"Debug | Poll: ", response)
        return response

    def get_events(self, pool):
        response = {'messages': [], 'actions': []}
        for result in pool:
            if 'message' in result.keys():
                message = result["message"]
                if 'text' in message.keys():
                    response['messages'].append(
                        {'msg_id': message['message_id'], 'from_id': message['from']['id'],
                         'chat_id': message['chat']['id'],
                         'text': message['text'], 'name': message['from']['first_name']})
            elif 'my_chat_member' in result.keys():
                actions = result["my_chat_member"]
                if actions["chat"]["type"] == "channel":
                    if actions["new_chat_member"]["user"]["id"] == self.id:
                        if actions["new_chat_member"]["status"] in ["left", "kicked"]:
                            response['actions'].append({'action': 'channel_delete', 'chat_id': actions["chat"]['id']})
                        else:
                            response['actions'].append({'action': 'channel_add', 'chat_id': actions["chat"]['id']})
            elif 'callback_query' in result.keys():
                actions = result["callback_query"]
                data = actions['data'].split(';')
                response['actions'].append({'action': data[0], 'msg_id': actions['message']['message_id'],
                                            'from_id': actions['from']['id'],
                                            'chat_id': actions['message']["chat"]['id'],
                                            'callback_id': actions['id'], "data": data[1].split(':')})
            elif 'channel_post' in result.keys():
                actions = result["channel_post"]
                response['actions'].append(
                    {'action': 'channel_post', 'msg_id': actions['message_id'],
                     'chat_id': actions["chat"]['id']})

        return response

    @staticmethod
    def send_notification(callback_query_id, popup_text, url=None, popup=True):
        try:
            if url is None:
                BOT.method('answerCallbackQuery', callback_query_id=act['callback_id'],
                           text=popup_text,
                           show_alert=popup)
            else:
                BOT.method('answerCallbackQuery', callback_query_id=act['callback_id'],
                           text=popup_text,
                           show_alert=popup, url=url)
        except ExceptionTGMSG as exc:
            if exc.code == 400:
                return

    @staticmethod
    def send_message(send_text, chat_id, **kwargs):
        return BOT.method(name='sendMessage', chat_id=chat_id, text=send_text, disable_web_page_preview=True, **kwargs)


class EvgenyBot(TGBot):

    def __init__(self, token, debug=False):
        super().__init__(token, debug)

    def checkSubscribe(self, user_id, chat_id):
        try:
            response = self.method('getChatMember', user_id=user_id, raw=True, chat_id=chat_id)
            if not response['ok']:
                if response['error_code'] in 403:
                    raise ExceptionTGMSG(response['description'],
                                         response['error_code'])
                if response['error_code'] in 400:
                    return False
            if response['result']['status'] == 'left':
                return False
        except:
            print("Suka")
            return True
        return True

    def get_channelButton(self, database, from_id):
        buttons = []
        for channel_id, channel in database['channels'].items():
            invite_link = channel['invite_link'].replace('+', '%2b')
            if ( not self.checkSubscribe(from_id, channel_id) ) and channel['uses']['current'] < channel['uses']['max']:
                buttons.append([{"text": channel["title"], "url": invite_link}])
        return buttons


def channel_status(database, channel_id):
    if channel_id in database['channels'].keys():
        return "✅", database['channels'][channel_id]
    elif channel_id in database['new_channels'].keys():
        return "❌", database['new_channels'][channel_id]
    return False, None


def save_data(database, filename='database.json'):
    json_string = json.dumps(database, ensure_ascii=False).encode('utf8')
    with open(filename, 'wb') as outfile:
        outfile.write(json_string)


def mainButtons(channel_id):
    return [
        [{"text": '❌Удалить канал❌', "callback_data": f"chnMng;d:{channel_id}"}],
        [{"text": '🛠Переключить статус канала🛠', "callback_data": f"chnMng;c:{channel_id}"}],
        [{"text": '🚷Изменить лимиты переходов🚷', "callback_data": f"chnMng;l:{channel_id}"}],
        [{"text": '📍Изменить ссылку📍', "callback_data": f"chnMng;i:{channel_id}"}],
        [{"text": 'Назад', "callback_data": f"chnMng;o:0"}]
    ]


def panel(database, user):
    buttons = [
        [{"text": '🚧Управление каналами🚧', "callback_data": f"chnMng;o:0"}],
        [{"text": '💰Изменить награду💰', "callback_data": f"chnRwd;o:0"}]
    ]
    if user in database['owners']:
        buttons.append([{"text": '👨‍💼Управление админами👨‍💼', "callback_data": f"admMng;o"}])
        buttons.append([{"text": '❌Сбросить запуски❌', "callback_data": f"rstRns;o"}])
    passed_channels = 0
    text_append = ''
    channel_number = 0
    for channel_id, channel in database['channels'].items():
        channel_number+=1
        if channel['uses']['current'] >= channel['uses']['max']:
            passed_channels += 1

        text_append += f"\n\n{channel_number}: {channel['title']}:   {channel['uses']['current']} / {channel['uses']['max']}"

    text = f"[Админ панель]\n\n🤖Cтатистика по боту🤖\n❗Запусков бота: {database['stats']['start']}\n✅Полученных наград: {database['stats']['end']}\n\n🏆Cтатистика по активным каналам🏆\n❗Активных каналов: {len(database['channels'])}\n🎯Выполненных каналов: {passed_channels}\n" + text_append
    return text, buttons


def admin_code(database, code, chat_id, user_id, name=False):
    try:
        if code in database["admin_code"]:
            database["admin_code"].remove(code)
            if name:
                database["admins"][str(user_id)] = {"name": name}
            else:
                database["admins"][str(user_id)] = {"name": user_id}
            save_data(database)
            BOT.send_message(send_text="Теперь вы админ. Введите /start для открытия админ панели", chat_id=chat_id)
    except ValueError:
        BOT.send_message(send_text="Ваш код не действителен", chat_id=chat_id)
    return database


with open('database.json', 'r', encoding='utf-8') as f:  # открыли файл с данными
    database = json.load(f)  # загнали все, что получилось в переменную
#BOT = EvgenyBot('5169189756:AAG83jWE7euED8fABalO_aky5HZJXiW5D0k', DEBUG)
BOT = EvgenyBot(TOKEN, DEBUG)
Actions = Actions()

while True:
    try:
        events = BOT.get_events(BOT.get_pool())
        for msg in events['messages']:
            if str(msg['from_id']) in database['admins'].keys():
                database['admins'][str(msg['from_id'])]['name'] = msg['name']
                save_data(database)
            if str(msg['chat_id']) in database['blackList']:
                BOT.method('leaveChat', chat_id=msg['chat_id'])
                continue
            if Actions.compare_word(text_1=msg['text'], text_2=["/start"], accuracy=1):
                if msg['from_id'] in database['owners'] or str(msg['from_id']) in database['admins'].keys():
                    text, buttons = panel(database, msg['from_id'])
                    reply_markup = json.dumps({"inline_keyboard": buttons})
                    BOT.send_message(chat_id=msg['chat_id'], send_text=text, reply_markup=reply_markup)
                else:
                    buttons = BOT.get_channelButton(database, msg['from_id'])
                    if len(buttons) != 0:
                        buttons.append([{"text": '✅Проверить подписки✅', "callback_data": f"checkSubs;0"}])
                        reply_markup = json.dumps({"inline_keyboard": buttons})
                        text = "🔞*Чтобы получить доступ к СЛИВУ, ПОДПИШИСЬ на эти каналы и получишь СЕКРЕТНЫЙ КОНТЕНТ*🔞👇"
                        BOT.send_message(chat_id=msg['chat_id'], send_text=text, reply_markup=reply_markup, parse_mode="Markdown")
                        database['stats']['start'] += 1
                        save_data(database)
                    else:
                        buttons.append([{"text": '👇👇👇', "url": database["reward_url"]}])
                        buttons.append([{"text": '🔞Слив🔞', "url": database["reward_url"]}])
                        reply_markup = json.dumps({"inline_keyboard": buttons})
                        text = '🔥*Отлично, ты получил слив, жми на кнопку*🔥'
                        BOT.send_message(chat_id=msg['chat_id'], send_text=text, reply_markup=reply_markup, parse_mode="Markdown")
            elif Actions.compare_first_word(text_1=msg['text'], text_2=["/code"], accuracy=1):
                if msg['from_id'] in database['owners'] or str(msg['from_id']) in database['admins'].keys():
                    BOT.send_message(chat_id=msg['chat_id'], send_text="Вы уже админ")
                    continue
                text = msg['text'].split()
                if len(text) > 1:
                    database = admin_code(database, text[1], msg['chat_id'], msg['from_id'], msg['name'])
                    save_data(database)
                else:
                    database['sessions'][str(msg['from_id'])] = {'chat_id': msg['chat_id'], 'msg_id': msg['msg_id'],
                                                            'data': {'action': 'admin_code'}}
                    save_data(database)
                    text = 'Введите админ код'
                    BOT.send_message(chat_id=msg['chat_id'], send_text=text)
            else:
                if str(msg["from_id"]) in str(database['sessions'].keys()):
                    from_id = str(msg["from_id"])
                    print(database['sessions'].keys())
                    session = database['sessions'][str(from_id)]
                    text = f"[Админ панель]\n"
                    action = session["data"]['action']
                    if action == 'admin_code':
                        database = admin_code(database, msg['text'], msg['chat_id'], from_id, msg['name'])
                        database['sessions'].pop(str(from_id), None)
                        save_data(database)
                        BOT.send_message(send_text="Теперь вы админ. Введите /start для открытия админ панели", chat_id=msg['chat_id'])
                        continue
                    elif action == 'change_reward':
                        database['reward_url'] = msg['text']
                        database['sessions'].pop(str(from_id), None)
                        save_data(database)
                        text, buttons = panel(database, msg['from_id'])
                        text += '\nНаграда измененна'
                    elif action == 'change_invite_link':
                        status, channel = channel_status(database, session['data']['channel_id'])
                        if status:
                            channel["invite_link"] = msg['text']
                            database['sessions'].pop(str(msg["from_id"]), None)
                            save_data(database)
                            text += f"⚙️Управление каналом⚙️ \n\n{channel['title']}\n\nСтатус: {status}\nПереходы: {channel['uses']['current']} / {channel['uses']['max']}\nСсылка: {channel['invite_link'].replace('+', '%2b')}\n\nСсылка изменна"
                            buttons = mainButtons(channel_id)
                        else:
                            text += f"\nКанал не найден"
                            buttons = [
                                [{"text": 'Назад', "callback_data": f"chnMng;o:0"}],
                            ]
                    elif action in ["change_current_limit", "change_max_limit"]:
                        try:
                            new_limit = int(msg['text'])
                            status, channel = channel_status(database, session['data']['channel_id'])
                            if status:
                                if action == "change_current_limit":
                                    channel['uses']['current'] = new_limit
                                    word = 'текущих'
                                else:
                                    channel['uses']['max'] = new_limit
                                    word = 'максимальных'
                                database['sessions'].pop(str(from_id), None)
                                save_data(database)
                                text += f"⚙️Управление каналом⚙️ \n\n{channel['title']}\n\nСтатус: {status}\nПереходы: {channel['uses']['current']} / {channel['uses']['max']}\nСсылка: {channel['invite_link'].replace('+', '%2b')}\n\nИзменено значение {word} переходов"
                                buttons = mainButtons(session['data']['channel_id'])
                                reply_markup = json.dumps({"inline_keyboard": buttons})
                            else:
                                text += f"\nКанал не найден"
                                buttons = [
                                    [{"text": 'Назад', "callback_data": f"chnMng;o:0"}],
                                ]
                        except ValueError:
                            text += f"\nОшибка при преобразовании сообщения в число. Ваша админ сессия остановленна"
                            buttons = [
                                [{"text": 'Назад', "callback_data": f"chnMng;o:0"}],
                            ]
                    reply_markup = json.dumps({"inline_keyboard": buttons})
                    BOT.send_message(send_text=text, chat_id=session['chat_id'], reply_markup=reply_markup)

        for act in events['actions']:
            if act['action'] == 'channel_add':
                if str(act['chat_id']) in database['blackList']:
                    continue
                channel = BOT.method('getChat', chat_id=act['chat_id'])
                if not "invite_link" in channel.keys():
                    channel["invite_link"] = f"tg://user?id={BOT.id}"
                new_channel = {"title": channel["title"], "invite_link": channel["invite_link"],
                               "uses": {"max": 0, "current": 0}}
                database['new_channels'][str(act['chat_id'])] = new_channel
                save_data(database)
                continue

            elif act['action'] == 'channel_delete':
                database['channels'].pop(str(act['chat_id']), None)
                database['new_channels'].pop(str(act['chat_id']), None)
                save_data(database)
                continue

            elif act['action'] == 'channel_post':
                if str(act['chat_id']) in database['blackList']:
                    BOT.method('leaveChat', chat_id=act['chat_id'])
                    continue

            elif act['action'] == 'checkSubs':
                buttons = BOT.get_channelButton(database, act['from_id'])
                if len(buttons) != 0:
                    BOT.send_notification(act['callback_id'], 'Проверь подписку на все каналы и получи доступ🔞')
                    # Костыль с русским и английским символом, что бы телеграмм не ругался message is not modified
                    if act['data'][0] == '0':
                        o = 'o'  # eng
                    else:
                        o = 'о'  # rus
                    text = f'🔞Чт{o}бы получить слив, подпишись на эти каналы и после подписки ты получишь доступ к СЕКРЕТНОМУ КОНТЕНТУ🔥🔞'
                    # Так надёжнее чем хранить инфу о изменениях

                    buttons.append(
                        [{"text": '✅Проверить подписки✅', "callback_data": f"checkSubs;{abs(int(act['data'][0]) - 1)}"}])

                else:
                    for channel_id, channel in database['channels'].items():
                        if channel['uses']['current'] < channel['uses']['max']:
                            channel['uses']['current'] += 1
                            save_data(database)
                    buttons.append([{"text": '👇👇👇', "url": database["reward_url"]}])
                    buttons.append([{"text": '🔞Слив🔞', "url": database["reward_url"]}])
                    reply_markup = json.dumps({"inline_keyboard": buttons})
                    text = '🔥Отлично, ты получил слив, жми на кнопку🔥'
                    database['stats']['end'] += 1
                    save_data(database)

            elif str(act['from_id']) in database['admins'] or act['from_id'] in database['owners']:

                if act['action'] == 'panel':
                    text, buttons = panel(database, act['from_id'])

                elif act['action'] == 'rstRns':
                    database["stats"]["start"] = 0
                    database["stats"]["end"] = 0
                    save_data(database)
                    text, buttons = panel(database, act['from_id'])
                    text += "\n\nЗапуски сброшены"



                elif act['action'] == 'chnRwd':
                    from_id = str(act['from_id'])
                    if act['data'][0] == 'o':
                        text = '[Админ панель]\n💰Измененние награды💰\n\nВведите ссылку для награды'
                        buttons = [
                            [{"text": 'отмена', "callback_data": f"chnRwd;c:0"}]
                        ]
                        database['sessions'][str(from_id)] = {'chat_id': act['chat_id'], 'msg_id': act['msg_id'],
                                                         'data': {'action': 'change_reward'}}
                        save_data(database)

                    elif act['data'][0] == 'c':
                        database['sessions'].pop(str(from_id),None)
                        save_data(database)
                        text, buttons = panel(database, act['from_id'])

                elif act['action'] == 'chnMng':
                    buttons = []
                    channel_id = act['data'][1]
                    status, channel = channel_status(database, channel_id)
                    if act['data'][0] == 'o':
                        text = '[Админ панель]\n🚧Управление каналами🚧\n\n'
                        buttons = [
                            [{"text": 'Настройка активных каналов', "callback_data": f"chnMng;a:0"}],
                            [{"text": 'Настройка неактивных каналов', "callback_data": f"chnMng;u:0"}],
                            [{"text": 'Назад', "callback_data": f"panel;o:0"}]
                        ]

                    elif act['data'][0] == 'a':
                        text = '[Админ панель]\n🚀Aктивные каналы🚀\n⚙️Выберите канал для управления⚙️'
                        buttons = [
                            [{"text": 'Назад', "callback_data": f"panel;o:0"}]
                        ]
                        for channel_id, channel in database['channels'].items():
                            buttons.append([{"text": channel["title"], "callback_data": f"chnMng;m:{channel_id}"}])

                    elif act['data'][0] == 'u':
                        text = '[Админ панель]\n❌Неактивные каналы❌\n⚙️Выберите канал для управления⚙️'
                        buttons = [
                            [{"text": 'Назад', "callback_data": f"panel;o:0"}]
                        ]
                        for channel_id, channel in database['new_channels'].items():
                            buttons.append([{"text": channel["title"], "callback_data": f"chnMng;m:{channel_id}"}])

                    elif act['data'][0] == 'm':
                        text = '[Админ панел]\n'

                        if status:
                            text += f"⚙️Управление каналом⚙️ \n\n{channel['title']}\n\nСтатус: {status}\nПереходы: {channel['uses']['current']} / {channel['uses']['max']}\nСсылка: {channel['invite_link'].replace('+', '%2b')}"
                            buttons = mainButtons(channel_id)
                        else:
                            text += 'Канал не найден'
                            buttons = [
                                [{"text": 'Назад', "callback_data": f"chnMng;o:0"}],
                            ]

                    elif act['data'][0] == 'd':
                        text = f"[Админ панель]\n❌ Удаление канала ❌"
                        if status:
                            text += f"\n\n{channel['title']}\n\n❗Чтобы удалить канал {channel['title']} удалитите @{BOT.nick} из пользователей этого канала\n\n❗❗Вы можете заблокировать канал, но это необратимое действие (вернуть бота в каннал не получиться)\n\nСсылка: {channel['invite_link'].replace('+', '%2b')}\n\n"
                            buttons = [[{"text": 'Заблокировать канал', "callback_data": f"chnMng;b:{channel_id}"}],
                                       [{"text": 'Назад', "callback_data": f"panel;o:0"}]]
                        else:
                            text += 'Канал не найден'
                            buttons = [
                                [{"text": 'Назад', "callback_data": f"chnMng;o:0"}],
                            ]

                    elif act['data'][0] in ['b', 'e']:
                        text = f"[Админ панель]\nБлокировка канала: "
                        if status:
                            if act['data'][0] == 'e':
                                text += f"\n\n{channel['title']}\n\nКанал \n\n{channel['title']} был удалён\n\nСсылка: {channel['invite_link'].replace('+', '%2b')}\n\n"
                            else:
                                text += f"Канал \n\n{channel['title']} был заблокирован\nВы больше не сможете вернуть бота в него\n\nСсылка: {channel['invite_link'].replace('+', '%2b')}\n\n"
                                database['blackList'].append(channel_id)
                            buttons = [[{"text": 'Назад', "callback_data": f"chnMng;m:{channel_id}"}]]
                            BOT.method('leaveChat', chat_id=channel_id)
                            database['channels'].pop(channel_id, None)
                            save_data(database)

                        else:
                            text += 'Канал не найден'
                            buttons = [
                                [{"text": 'Назад', "callback_data": f"chnMng;o:0"}],
                            ]


                    elif act['data'][0] == 'c':
                        text = '[Админ панель]\n'
                        if status:
                            text += f"⚙️Управление каналом⚙️ \n\n{channel['title']}\n\n"
                            if status == '✅':
                                database['new_channels'][channel_id] = database['channels'].pop(channel_id)
                                text += f"Статус: ❌ (Канал был деактивирован)\n"
                            elif status == '❌':
                                database['channels'][channel_id] = database['new_channels'].pop(channel_id)
                                text += f"Статус: ✅ (Канал был aктивирован)\n"
                            save_data(database)
                            text += f"Переходы: {channel['uses']['current']} / {channel['uses']['max']}\nСсылка: {channel['invite_link'].replace('+', '%2b')}"
                            buttons = mainButtons(channel_id)
                        else:
                            text += 'Канал не найден'
                            buttons = [
                                [{"text": 'Назад', "callback_data": f"chnMng;o:0"}],
                            ]
                    elif act['data'][0] == 'l':
                        text = '[Админ панель]\n'
                        if status:
                            text += f"⚙️Управление каналом⚙️ \n\n{channel['title']}\n\nПереходы: {channel['uses']['current']} / {channel['uses']['max']}\nСсылка: {channel['invite_link'].replace('+', '%2b')}\n\nИзменеие переходов"

                            buttons = [
                                [{"text": 'Изменить текущие', "callback_data": f"chnMng;t:{channel_id}"}],
                                [{"text": 'Изменить макисмальные', "callback_data": f"chnMng;x:{channel_id}"}],
                                [{"text": 'Назад', "callback_data": f"chnMng;m:{channel_id}"}]
                            ]
                        else:
                            text += 'Канал не найден'
                            buttons = [
                                [{"text": 'Назад', "callback_data": f"chnMng;o:0"}],
                            ]

                    elif act['data'][0] == 't':
                        text = f"[Админ панель]\n⚙️Управление каналом⚙️ "
                        if status:
                            text += f"\n\n{channel['title']}\n\nПереходы: {channel['uses']['current']} (введите новое значение) / {channel['uses']['max']}\n\nВведите новое значение текущих переходов: "
                            database['sessions'][str(act['from_id'])] = {'chat_id': act['chat_id'], 'msg_id': act['msg_id'],
                                                                    'data': {'action': 'change_current_limit',
                                                                             'channel_id': channel_id}}
                            buttons = [
                                [{"text": 'Отмена', "callback_data": f"chnMng;q:{channel_id}"}],
                            ]
                        else:
                            text += 'Канал не найден'
                            buttons = [
                                [{"text": 'Назад', "callback_data": f"chnMng;o:0"}],
                            ]
                    elif act['data'][0] == 'x':
                        text = f"[Админ панель]\n⚙️Управление каналом⚙️ "
                        if status:
                            text += f"\n\n{channel['title']}\n\nПереходы: {channel['uses']['current']} / {channel['uses']['max']} (введите новое значение)\n\nВведите новое значение максимальных переходов: "
                            database['sessions'][str(act['from_id'])] = {'chat_id': act['chat_id'], 'msg_id': act['msg_id'],
                                                                    'data': {'action': 'change_max_limit',
                                                                             'channel_id': channel_id}}
                            save_data(database)
                            buttons = [
                                [{"text": 'Отмена', "callback_data": f"chnMng;q:{channel_id}"}],
                            ]
                        else:
                            text += 'Канал не найден'
                            buttons = [
                                [{"text": 'Назад', "callback_data": f"chnMng;o:0"}],
                            ]

                    elif act['data'][0] == 'i':
                        text = f"[Админ панель]\n⚙️Управление каналом⚙️ "
                        if status:
                            text += f"\n\n{channel['title']}\n\n🛠Изменение ссылки🛠\n📍Текущая ссылка: {channel['invite_link'].replace('+', '%2b')}\n\nВведите новую ссылку👇"
                            database['sessions'][str(act['from_id'])] = {'chat_id': act['chat_id'], 'msg_id': act['msg_id'],
                                                                    'data': {'action': 'change_invite_link',
                                                                             'channel_id': channel_id}}
                            buttons = [
                                [{"text": 'Отмена', "callback_data": f"chnMng;q:{channel_id}"}],
                            ]
                        else:
                            text += 'Канал не найден'
                            buttons = [
                                [{"text": 'Назад', "callback_data": f"chnMng;o:0"}],
                            ]

                    elif act['data'][0] == 'q':
                        text = f"[Админ панель]\n⚙️Управление каналом⚙️ "
                        if act["from_id"] in database['sessions'].keys():
                            database['sessions'].pop(str(act["from_id"]), None)
                            if status:
                                text += f"\n\n{channel['title']}⚙️Управление каналом⚙️ \n\n{channel['title']}\n\nПереходы: {channel['uses']['current']}/ {channel['uses']['max']}\nСсылка: {channel['invite_link'].replace('+', '%2b')}\n\n"
                                buttons = mainButtons(channel_id)
                            else:
                                text += '\nКанал не найден'
                                buttons = [
                                    [{"text": 'Назад', "callback_data": f"chnMng;o:0"}],
                                ]
                        else:
                            text = f"[Админ панель]\nОшибка ключа сессии. Сессия оконченна\n\n"
                    else:
                        continue
                elif act['action'] == 'admMng':
                    if act['data'][0] == 'o':
                        text = "[Админ панел]\n👨‍💼Управление админами👨‍💼"
                        buttons = [
                            [{"text": 'Назад', "callback_data": f"panel;o:0"}],
                            [{"text": "Добавить админа", "callback_data": f"admMng;a:0"}]
                        ]
                        for id in database['admins']:
                            buttons.append([{"text": database['admins'][id]['name'], "callback_data": f"admMng;m:{id}"}])
                    elif act['data'][0] == 'm':
                        text = "[Админ панел]\n👨‍💼Управление админами👨‍💼\n\n"

                        if act['data'][1] in database['admins'].keys():
                            admin = database['admins'][act['data'][1]]
                            text += f"Админ {admin['name']}"
                            buttons = [
                                [{"text": 'Информация', "url": f"tg://user?id={act['data'][1]}"}],
                                [{"text": 'Удалить', "callback_data": f"admMng;d:{act['data'][1]}"}],
                                [{"text": 'Назад', "callback_data": f"admMng;o:0"}],

                            ]
                        else:
                            text += 'Админ не найден'
                            buttons = [
                                [{"text": 'Назад', "callback_data": f"admMng;o:0"}],
                            ]

                    elif act['data'][0] == 'a':
                        text = "[Админ панел]\n👨‍💼Добавление админа👨‍💼\n\nЧтобы использовать код:\n/code (код)\n"
                        buttons = [
                            [{"text": 'Назад', "callback_data": f"admMng;o:0"}],
                            [{"text": 'Сгенерировать новый код', "callback_data": f"admMng;n:0"}]
                        ]
                        for code in database['admin_code']:
                            buttons.append([{"text": code, "callback_data": f"admMng;c:{code}"}])

                    elif act['data'][0] == 'c':
                        text = "[Админ панел]\n👨‍💼Добавление админа👨‍💼\n\n❗❗Нажмите на код что, бы удалить его\n Использование:\n/code (код)\n\n(Для удаления существующего кода, нажмите на него)"
                        buttons = [
                            [{"text": 'Назад', "callback_data": f"admMng;o:0"}],
                            [{"text": 'Сгенерировать новый код', "callback_data": f"admMng;n:0"}]
                        ]
                        code = act['data'][1]
                        try:
                            database['admin_code'].remove(code)
                            save_data(database)
                        except:
                            text += "Код не найден"
                        for code in database['admin_code']:
                            buttons.append([{"text": code, "callback_data": f"admMng;c:{code}"}])

                    elif act['data'][0] == 'n':
                        text = "[Админ панел]\n👨‍💼Добавление админа👨‍💼\n\n"
                        code = random.randint(0, 999999)
                        code = f'{code:06}'
                        database['admin_code'].append(code)
                        save_data(database)
                        text += f"Код для получения прав администратора: {code}\n Использование:\n/code {code}"
                        buttons = [
                            [{"text": 'Назад', "callback_data": f"admMng;a:0"}]
                        ]

                    elif act['data'][0] == 'd':
                        text = "[Админ панел]\nУдаление админами:\n\n"
                        if act['data'][1] in database['admins'].keys():
                                database['admins'].pop(act['data'][1], None)
                                save_data(database)
                                text += f"Админ {act['data'][1]} удалён"
                                buttons = [
                                    [{"text": 'Информация', "url": f"tg://user?id={act['data'][1]}"}],
                                    [{"text": 'Назад', "callback_data": f"admMng;o:0"}],
                                ]
                        else:
                            text += 'Админ не найден'
                            buttons = [
                                [{"text": 'Назад', "callback_data": f"admMng;o:0"}],
                            ]

            else:
                BOT.method('deleteMessage', chat_id=act['chat_id'], message_id=act['msg_id'])
                continue

            reply_markup = json.dumps({"inline_keyboard": buttons})
            try:
                BOT.method('editMessageText', disable_web_page_preview=True, chat_id=act['chat_id'], message_id=act['msg_id'],
                           text=text,
                           reply_markup=reply_markup)
            except:
                continue
    except BaseException as exc:
        print(exc)
        continue
