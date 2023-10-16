import json
from datetime import datetime, timedelta
from sqlite3 import Cursor
from typing import Any

from interactions import GuildText, EmbedFooter, MaterialColours, GuildCategory

from const import LANGUAGES

EMBED_PRIMARY = MaterialColours.DEEP_PURPLE
EMBED_SECONDARY = MaterialColours.PURPLE

FOOTER = EmbedFooter(text='disclate ・ v1.0')

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


async def get_auto_delete_timer_string(cooldown: int | str | None, can_inherit: bool = True) -> str:
    """ Returns the label for the auto delete timer """
    if cooldown:
        cooldown = int(cooldown)
        for label, seconds in AUTO_DELETE_TIMERS:
            if cooldown == seconds:
                return label
    if can_inherit:
        return 'Inherit'
    return 'Never delete'


async def find_in_list(data_list: [dict], value: Any, key: str) -> dict:
    """ Finds an item in a list of dictionaries by a given key and value """
    item = next((item for item in data_list
                 if item[key] == int(value)), None)
    if not item:
        print(f'WARNING: Did not find {key} {item} in {data_list}')
    return item


def get_language_name(language_code: str, add_native: bool = False, native_only: bool = False) -> str:
    """ Returns the name of a language from its code """
    for lang in LANGUAGES:
        if lang['iso'] == language_code:
            if native_only:
                return lang['native']
            return lang['name'] + (f' ({lang["native"]})' if add_native else '')
    return f'Unknown: {language_code}'


async def language_list_string(data: dict) -> str:
    """ Returns a string of all languages in a list """
    if not data or not data['auto_translate']:
        string = '`None`'
    else:
        name_list = [f'`{get_language_name(language)}`'
                     for language in json.loads(data['auto_translate'])]
        string = '\n'.join(name_list)

    return string


async def channel_list_string(text_channel_list: [GuildText], selected_category: GuildCategory,
                              max_length: int = 5) -> str:
    """ Returns a string of all languages in a list """
    affected_channels = [
        f'{channel.mention}' for channel in text_channel_list
        if channel.parent_id == selected_category.id]
    if not affected_channels:
        return '*No text channels associated with this category.*'
    elif len(affected_channels) > max_length:
        total_channels = len(affected_channels)
        affected_channels = affected_channels[:max_length]
        affected_channels.append(f'*+ {total_channels - max_length} more...*')
    string = '\n'.join(affected_channels)
    return string


async def get_total_links(cursor: Cursor, channel_ids: list[int | str]) -> int:
    """ Returns the number of links created for a channel"""
    cursor.execute("SELECT COUNT(*) FROM channel_link "
                   f"WHERE channel_from_id IN ({('?,' * (len(channel_ids) - 1))}?)",
                   channel_ids)
    return cursor.fetchone()[0]


async def group_channel_links(selected_channel: GuildText, links_query: list) -> list:
    """ Returns a list of lists of channel links, joined on their auto_translate languages"""
    if not links_query:
        return []
    channel_groups = []

    for row in links_query:
        row = dict(row)
        row['languages'] = json.loads(row['languages'])
        row['languages'].sort()
        found_group = False
        for group in channel_groups:
            if row['languages'] == group['languages']:
                group['channels'].append(row['channel_to_id'])
                found_group = True
                break
            if row['channel_to_id'] in group['channels']:
                group['languages'].extend(row['languages'])
                group['languages'].sort()
                found_group = True
                break
        if not found_group:
            channel_groups.append({'channels': [row['channel_to_id']], 'languages': row['languages']})
    return channel_groups


def db_timestamp(days_offset: int = 0):
    """ Returns the current timestamp in the TEXT format used by the database """
    return (datetime.now() - timedelta(days=days_offset)).strftime('%Y-%m-%d')
