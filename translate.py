import os
import time

import openai
import six
from dotenv import load_dotenv
from google.api_core.exceptions import BadRequest
from google.cloud import translate_v2 as translate
from utils import get_language_name

from constants import LANGUAGES, GPT_LANGUAGES

load_dotenv()
GOOGLE_APPLICATION_CREDENTIALS = os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = "service_account.json"
openai.api_key = os.getenv("CHATGPT_TOKEN")


class FailedTranslation(BaseException):
    pass


TRANSLATION_CLIENT = translate.Client()


async def translate_text(targets: [str], text: str) -> [dict]:
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
                # response = response.replace('\n', '')
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
    return translation_data


async def gpt_translate(text: str, target: str) -> dict:
    prompt = f'Translate the following text to {get_language_name(target)}, ' \
             f'do not include any other text but the translation: \n\n"""{text}"""'
    print(prompt)
    response = openai.ChatCompletion.create(
        model='gpt-3.5-turbo',
        messages=[
            {'role': 'system', 'content': prompt}
        ]
    )
    print(response)
    return response


async def detect_text_language(text: str) -> dict:
    """ Detect the language of any text, with confidence rating"""
    result = TRANSLATION_CLIENT.detect_language(text)

    print("Text: {}".format(text))
    print("Confidence: {}".format(result["confidence"]))
    print("Language: {}".format(result["language"]))

    return result


async def create_detection_embed(detection_data: dict):
    """ Create embed for language detection functionality"""
    pass


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


async def create_translation_embed(translation_data):
    """ Create embed for language translation functionality"""
    

# Text can also be a sequence of strings, in which case this method
# will return a sequence of results for each text.

# print flag and langs for all flag data
# for flag, langs in FLAG_DATA.items():
#     print(flag, langs)
# translations = await translate_text(['fr', 'en'], 'Die lust ik ook🙂, maar als ik mag kiezen dan liever een worstenbroodje van de echte bakker.')
# print(translations)
