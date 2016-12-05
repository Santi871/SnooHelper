import configparser


def get_token(token_name, section, config_name='config.ini'):

    """Get token from .ini file"""

    config = configparser.ConfigParser()
    config.read(config_name)
    token = config.get(section, token_name)
    return token
