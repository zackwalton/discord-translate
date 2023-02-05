import os
import time

import six
from google.api_core.exceptions import BadRequest
from google.cloud import translate_v2 as translate

GOOGLE_APPLICATION_CREDENTIALS = os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = "service_account.json"


class FailedTranslation(BaseException):
    pass


def translate_text(targets: [str], text: str) -> [dict]:
    """ Translates text into all target languages using the Google Cloud Translation API

    Args:
        targets: List of all target translation languages e.g. ['en', 'fr']
        text: Text to translate to all target languages
    Returns:
        [dict]: List of dictionaries containing all translation data, a single dict per target language

    """
    client = translate.Client()

    if not isinstance(targets, list):  # convert to list
        targets = [targets]

    if isinstance(text, six.binary_type):  # decode if required
        text = text.decode("utf-8")

    print(f'TARGETS: {targets}')
    translation_data = []
    for target in targets:
        try:
            start_time = time.time()
            result = client.translate(text, target_language=target, format_='text')
            end_time = time.time()
            print(f"DEBUG: Translation took: {end_time - start_time:.2f} seconds")
            result['targetLanguage'] = target
            translation_data.append(result)
        except BadRequest:
            translation_data.append(FailedTranslation(f'Failed to translate to language: `{target}`'))
    print('\n')
    return translation_data


async def translation_tostring(translation_data: [dict]) -> str:
    string = ""

    multiple = len(translation_data) > 1

    for i, t in enumerate(translation_data):
        if i != 0 and i != len(translation_data):
            string += '\n\n'
        if multiple:
            string += f'`{t["targetLanguage"].upper()}:` '

        string += f'{t["translatedText"]}'

    return string

# data format
# [
#   {
#      'translatedText': "Je m'appelle Zachary Walton",
#      'detectedSourceLanguage': 'en',
#      'input': 'My name is Zachary Walton',
#      'targetLanguage': 'fr'
#    },
#    {
#      'translatedText': 'My name is Zachary Walton'
#      'detectedSourceLanguage': 'en',
#      'input': 'My name is Zachary Walton',
#      'targetLanguage': 'en'
#    }
# ]


# print flag and langs for all flag data
# for flag, langs in FLAG_DATA.items():
#     print(flag, langs)
# translations = translate_text(['fr', 'en'], 'My name is Zachary Walton')
# print(translations)
