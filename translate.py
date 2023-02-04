from google.cloud import translate_v2 as translate
import six
import os

GOOGLE_APPLICATION_CREDENTIALS = os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = "service_account.json"


def translate_text(target, text) -> [(str, str)]:
    """ Translates text into target language """
    client = translate.Client()

    if isinstance(text, six.binary_type):
        text = text.decode("utf-8")

    # todo decide the target(s) here

    # Text can also be a sequence of strings, in which case this method
    # will return a sequence of results for each text.
    result = client.translate(text, target_language=target, format_='text')

    print(u"Text: {}".format(result["input"]))
    print(u"Translation: {}".format(result["translatedText"]))
    print(u"Detected source language: {}".format(result["detectedSourceLanguage"]))

    return result['translatedText']


print(translate_text('fr', 'that was a crazy round, man, gg'))
