from snoohelper.database.models import FilterModel, db
import time
import re


class Filter:

    def __init__(self, filter_string, subreddit, use_regex, expires):
        self.filter_string = filter_string
        self.use_regex = use_regex
        self.expires = expires
        self.subreddit = subreddit
        self.split_filter = None
        self.split_regex = None

        if not use_regex:
            self.split_filter = self.filter_string.split(',')
        else:
            self.filter_string = self.filter_string.replace('"', "")
            self.filter_string = self.filter_string.replace("'", "")
            self.split_regex = self.filter_string.split(',')
        self.save()

    def save(self):
        db.connect()
        FilterModel.create(filter_string=self.filter_string, subreddit=self.subreddit, expires=self.expires,
                           use_regex=self.use_regex)
        db.close()

    def remove(self):
        db.connect()
        filter_obj = FilterModel.get(filter_string=self.filter_string, subreddit=self.subreddit)
        filter_obj.delete_instance()
        db.close()

    def has_expired(self):
        if time.time() > self.expires and self.expires:
            return True
        return False

    def check_filter(self, text):
        if not self.use_regex:
            for word in self.split_filter:
                if word in text:
                    return True
            return False
        else:
            for regex_pattern in self.split_regex:
                results = re.findall(regex_pattern, text)
                if results:
                    return True
            return False


class FiltersController:

    def __init__(self, subreddit):
        self.subreddit = subreddit
        self.filters = list()

        for filter_instance in FilterModel.select().where(FilterModel.subreddit == subreddit):
            self.add_filter(filter_string=filter_instance.filter_string, use_regex=filter_instance.use_regex,
                            expires=filter_instance.expires.timestamp())

    def add_filter(self, filter_string, use_regex, expires):
        filter_obj = Filter(filter_string=filter_string, use_regex=use_regex, subreddit=self.subreddit, expires=expires)
        self.filters.append(filter_obj)
        return filter_obj

    def remove_filter(self, filter_string):
        filter_obj = FilterModel.get(filter_string=filter_string, subreddit=self.subreddit)
        filter_obj.delete_instance()
        for filter_obj in self.filters:
            if filter_obj.filter_string == filter_string and filter_obj.subreddit == self.subreddit:
                self.filters.remove(filter_obj)
                break

    def check_all(self, text):
        for filter_obj in self.filters:
            expired = filter_obj.has_expired()
            if expired:
                self.remove_filter(filter_obj.filter_string)
                continue
            return filter_obj.check_filter(text), filter_obj
        return False
