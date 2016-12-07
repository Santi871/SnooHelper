import configparser
import os


def get_token(token_name, section, config_name='config.ini'):

    """Get token from .ini file"""

    config = configparser.ConfigParser()
    config.read(config_name)
    try:
        token = config.get(section, token_name)
    except configparser.NoSectionError:
        token = os.environ[token_name]

    return token
