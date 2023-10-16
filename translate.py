import os
import time
from pprint import pprint
from sqlite3 import Cursor

import openai
import six
from dotenv import load_dotenv
from google.api_core.exceptions import BadRequest
from google.cloud import translate_v2 as translate
from interactions import Embed, Member, User, EmbedAuthor, EmbedFooter

from const import GPT_LANGUAGES
from utils import get_language_name, EMBED_PRIMARY

load_dotenv()
GOOGLE_APPLICATION_CREDENTIALS = os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = "service_account.json"
openai.api_key = os.getenv("CHATGPT_TOKEN")


class FailedTranslation(BaseException):
    pass


TRANSLATION_CLIENT = translate.Client()


async def translate_text(targets: str | list[str], text: str) -> [dict]:
    """ Translates text into all target languages using the Google Cloud Translation API or GPT 3.5 Turbo
    Args:
        targets: List of all target translation languages e.g. ['en', 'fr']
        text: Text to translate to all target languages
    Returns:
        [dict]: List of dictionaries containing all translation data, a single dict per target language
    """

    if not isinstance(targets, list):  # convert to list
        targets = [targets]

    if isinstance(text, six.binary_type):  # decode if required
        text = text.decode("utf-8")

    print(f'TARGETS: {targets}')
    translation_data = []
    for target in targets:
        try:
            start_time = time.time()
            if target in GPT_LANGUAGES:
                response = (await gpt_translate(text, target))['choices'][0]['message']['content']
                result = {'translatedText': response}
            else:
                result = TRANSLATION_CLIENT.translate(text, target_language=target, format_='text')
                if result['detectedSourceLanguage'] == target:  # skip languages that are the same as the source
                    continue
            print(result)
            end_time = time.time()
            print(f"DEBUG: Translation took: {end_time - start_time:.2f} seconds")
            result['targetLanguage'] = target
            translation_data.append(result)
        except BadRequest:
            translation_data.append(FailedTranslation(f'`{target}`'))
    print('\n')
    pprint(translation_data)
    return translation_data


async def gpt_translate(text: str, target: str) -> dict:
    prompt = f'Translate the following text to {get_language_name(target)}, ' \
             f'do not include any other text but the translation: \n\n{text}'
    print(prompt)
    response = openai.ChatCompletion.create(
        model='gpt-3.5-turbo',
        messages=[
            {'role': 'user', 'content': prompt}
        ]
    )
    print(response)
    return response


async def create_trans_embed(translation_data: [dict], author: Member | User, target_langs: [str]) -> Embed:
    """ Create embed for language translation functionality"""
    source_lang = None
    if 'detectedSourceLanguage' in translation_data[0]:
        source_lang = translation_data[0]['detectedSourceLanguage']
        from_lang = f'{get_language_name(translation_data[0]["detectedSourceLanguage"], native_only=True)} → '
    else:
        from_lang = ''
    to_lang = f'{", ".join([get_language_name(e, native_only=True) for e in target_langs if e != source_lang])}'
    embed = Embed(
        author=EmbedAuthor(name=f'{author.nickname} ({author.global_name})'),
        description=(await translation_tostring(translation_data)),
        footer=EmbedFooter(text=f'{from_lang}{to_lang} ・ for {author.global_name}'),
        color=EMBED_PRIMARY
    )
    return embed


async def create_thread_trans_embed(translation_data: [dict], author: Member | User) -> Embed:
    """ Create embed for language translation functionality"""
    return Embed(
        author=EmbedAuthor(name=author.global_name, icon_url=author.avatar_url),
        description=(await translation_tostring(translation_data)),
        color=EMBED_PRIMARY,
    )


async def detect_text_language(text: str) -> dict:
    """ Detect the language of any text, with confidence rating"""
    result = TRANSLATION_CLIENT.detect_language(text)

    print("Text: {}".format(text))
    print("Confidence: {}".format(result["confidence"]))
    print("Language: {}".format(result["language"]))

    return result


async def create_detection_embed(detection_data: dict):
    """ Create embed for language detection functionality"""
    embed = Embed(

    )


async def translation_tostring(translation_data: [dict]) -> str:
    """ Build a string for the translation embed based on translation data """
    text = ""
    has_multiple_languages = len(translation_data) > 1

    for i, t in enumerate(translation_data):
        if i != 0 and i != len(translation_data):
            text += '\n\n'
        if isinstance(t, FailedTranslation):
            text += 'Language Failed.'
            continue
        if has_multiple_languages:
            text += f'`{t["targetLanguage"].upper()}:` '
        text += t["translatedText"]
    return text


async def get_guild_tokens(guild_id: int, cursor: Cursor) -> int:
    """ Check if a guild has enough tokens to translate """
    cursor.execute("SELECT tokens_remaining FROM guild WHERE id = ?", (guild_id,))
    remaining = cursor.fetchone()[0]
    if not remaining:
        return 0
    return remaining


async def spend_guild_tokens(guild_id: int, amount: int, cursor: Cursor) -> None:
    """ Spend tokens for a guild, must call commit() changes to database after calling this function """
    cursor.execute('''
    UPDATE guild 
        SET tokens_remaining = CASE 
            WHEN tokens_remaining < ? THEN 0 
            ELSE tokens_remaining - ? END
        WHERE id = ?
    ''', (amount, amount, guild_id))
