from reddit_interface import bot_threading
import utils.utils as utils
from time import sleep
from peewee import SqliteDatabase, Using, OperationalError, IntegrityError
from reddit_interface.database import UserModel, AlreadyDoneModel


class RedditBot:

    def __init__(self, team):
        self.config = team
        self.oauth_config_filename = team.team_name + "_oauth.ini"
        self.subreddit_name = team.subreddit
        self.db = SqliteDatabase(self.subreddit_name + '.db')
        self.db.connect()

        try:
            with Using(self.db, models=[UserModel, AlreadyDoneModel]):
                self.db.create_tables(models=[UserModel, AlreadyDoneModel])
        except OperationalError:
            pass

        self.already_done_helper = utils.AlreadyDoneHelper(self.db)
        self.scan_modlog()

    @bot_threading.own_thread
    def user_summary(self, r, o, user, request):
        response = utils.SlackResponse("Hi")
        sleep(5)
        request.delayed_response(response)

    @bot_threading.own_thread
    def scan_modlog(self, r, o):
        subreddit = r.get_subreddit(self.subreddit_name)

        while True:
            o.refresh()
            modlog = subreddit.get_mod_log(limit=100)

            for item in modlog:
                try:
                    self.already_done_helper.add(item.id)
                except IntegrityError:
                    continue

                with Using(self.db, [UserModel]):
                    user, _ = UserModel.get_or_create(username=item.target_author)
                    if item.action == 'removecomment':
                        user.removed_comments += 1
                    elif item.action == 'removelink':
                        user.removed_submissions += 1

                    user.save()

            sleep(10)








