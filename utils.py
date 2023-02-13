import time


def gen_countdown(offset: int) -> str:
    """ Generates a discord countdown with a given offset"""
    return f'<t:{round(time.time() + offset)}:R>'
