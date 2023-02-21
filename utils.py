import time
from typing import Any

from constants import LANGUAGES

EMBED_COLOUR = 0x56b0fd

AUTO_DELETE_TIMERS = [
    ('30 Seconds', 30),
    ('1 Minute', 60),
    ('2 Minutes', 120),
    ('5 Minutes', 300),
    ('15 Minutes', 900)
]

AUTO_TRANSLATE_OPTIONS = [
    'zh-CN', 'zh-TW', 'es', 'en', 'ar',
    'ko', 'pt', 'ru', 'ja', 'de',
    'vi', 'fr', 'it', 'tr', 'tl',
    'nl', 'th', 'hu', 'sv', 'da',
    'fi', 'sk', 'af', 'no', 'ga'
]

# list of all languages in a dict in the form of
# merge countries_temp and AUTO_TRANSLATE_SELECT_OPTIONS into list of tuples


def gen_countdown(offset: int) -> str:
    """ Generates a discord countdown with a given offset"""
    return f'<t:{round(time.time() + offset)}:R>'


def get_auto_delete_timer_string(cooldown: int | None, can_inherit: bool = True) -> str:
    """ Returns the label for the auto delete timer """
    if cooldown:
        for label, seconds in AUTO_DELETE_TIMERS:
            if cooldown == seconds:
                return label
    if can_inherit:
        return 'Inherit'
    return 'Never delete'


def find_in_list(data_list: [dict], value: Any, key: str) -> dict:
    """ Finds an item in a list of dictionaries by a given key and value """
    item = next((item for item in data_list
                 if item[key] == int(value)), None)
    if not item:
        print(f'WARNING: Did not find {key} {item} in {data_list}')
    return item


def get_language_name(language_code: str, add_native: bool = False) -> str:
    """ Returns the name of a language from its code """
    for lang in LANGUAGES:
        if lang['iso'] == language_code:
            return lang['name'] + (f' ({lang["native"]})' if add_native else '')
    return f'Unknown: {language_code}'
