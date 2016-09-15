import threading
import traceback
from time import sleep
import requests.exceptions
import praw
import OAuth2Util


class CreateThread(threading.Thread):
    def __init__(self, thread_id, name, obj, method, kwargs=None):
        threading.Thread.__init__(self)
        self.threadID = thread_id
        self.name = name
        self.obj = obj
        self.method = method
        self.kwargs = kwargs

    def run(self):
        # This loop will run when the thread raises an exception
        while True:
            try:
                methodToRun = self.method(self.obj, **self.kwargs)
                break
            except AssertionError:
                print("------------\nRan into an assertion error\nTrying again\n------------")
                sleep(1)
                print(traceback.format_exc())
                continue
            except (requests.exceptions.HTTPError, praw.errors.HTTPException):
                sleep(2)
                continue
            except:
                print("*Unhandled exception"
                      " in thread* '%s'." % self.name)
                print(traceback.format_exc())
                sleep(10)


def own_thread(func):
    def wrapped_f(*args, **kwargs):
        # Create a thread with the method we called
        if not kwargs:
            kwargs = None

        bot_obj = args[0]

        handler = praw.handlers.MultiprocessHandler()
        r = praw.Reddit(user_agent="windows:RedditSlacker2 0.1 by /u/santi871", handler=handler)
        o = OAuth2Util.OAuth2Util(r, configfile=bot_obj.oauth_config_filename)
        r.config.api_request_delay = 1
        o.refresh()

        if kwargs is not None:
            kwargs['r'] = r
            kwargs['o'] = o
        else:
            kwargs = {'r': r, 'o': o}

        thread = CreateThread(1, str(func) + " thread", args[0], func, kwargs)
        thread.start()

    return wrapped_f


