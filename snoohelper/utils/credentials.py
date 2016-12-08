import configparser
import os


def get_token(token_name, section, config_name='config.ini', is_bool=False):

    """Get token from .ini file"""

    config = configparser.ConfigParser()
    config.read(config_name)
    try:
        if not is_bool:
            token = config.get(section, token_name)
        else:
            token = config.getboolean(section, token_name)
    except configparser.NoSectionError:
        token = os.environ[token_name]

    return token
