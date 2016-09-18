import praw
from OAuth2Util import OAuth2Util
import configparser
from snoohelper.reddit_interface.bot_modules.spam_cruncher.user_analyzer import UserAnalyzer


class SCConfig:

    def __init__(self, filename, section='bot'):

        self.config = configparser.ConfigParser()
        self.filename = filename
        self.section = section

        self.debug_mode = None
        self.user_agent = None
        self.subreddit = None
        self.domain_whitelist = None
        self.filter_below = None
        self.get_comments = None

        self._update()

    def _update(self):

        self.config.read(self.filename)
        self.debug_mode = self.config.get(self.section, "debug_mode")
        self.user_agent = self.config.get(self.section, "user_agent")
        self.subreddit = self.config.get(self.section, "subreddit")
        self.filter_below = self.config.getint(self.section, "filter_below")
        self.get_comments = self.config.getboolean(self.section, "get_comments")
        self.domain_whitelist = self.config.get(self.section, "domain_whitelist").split(',')

    def get_domain_whitelist(self):
        return self.config.get(self.section, "domain_whitelist").split(',')

    def add_whitelisted_domain(self, domain):
        whitelist = self.config.get(self.section, "domain_whitelist")
        if not whitelist.endswith(','):
            whitelist += ','
        whitelist += domain + ","

        self.config['bot']['domain_whitelist'] = whitelist
        with open(self.filename, 'w') as configfile:
            self.config.write(configfile)

        self._update()


class SpamCruncher:

    def __init__(self, config):

        self.config = config
        self.r = praw.Reddit(self.config.user_agent)

        self._authenticate()
        self.user_analyzer = UserAnalyzer(self.r, self.config)

    def _authenticate(self):

        o = OAuth2Util(self.r, configfile=self.config.filename)
        o.refresh(force=True)
        self.r.config.api_request_delay = 1
        print("Running...")

    def analyze_stream(self, subreddit, filter_below=50, get_comments=False, verbose=False):
        stream = praw.helpers.comment_stream(self.r, subreddit, limit=5, verbosity=-1)

        for submission in stream:
            results = self.analyze_user(submission.author.name, get_comments=get_comments,
                                        verbose=verbose, filter_below=filter_below)
            if results.spammer_likelihood >= filter_below:
                print(results.get_json())
                print("Calculated spammer likelihood: " + str(results.spammer_likelihood))
                print("Userpage: https://reddit.com/u/" + results.user.name)

                if not verbose:
                    print("----------------------------")

            if verbose:
                print("----------------------------")

    def analyze_user(self, name, verbose=True, get_comments=False, filter_below=50):

        try:
            results = self.user_analyzer.analyze_user(name, get_comments=get_comments, verbose=verbose)
        except praw.errors.NotFound:
            results = "User not found"

        return results


