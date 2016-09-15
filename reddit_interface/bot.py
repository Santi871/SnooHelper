from reddit_interface import bot_threading


class RedditBot:

    def __init__(self, config):
        self.config = config
        self.oauth_config_filename = config.team_name + "_oauth.ini"

    @bot_threading.own_thread
    def user_summary(self, r, user):
        return "Hi"




