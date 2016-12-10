from peewee import IntegerField, TextField, Model, BooleanField, TimestampField, Proxy

db = Proxy()


class BaseModel(Model):
    class Meta:
        database = db


class UserModel(BaseModel):
    username = TextField()
    removed_comments = IntegerField(default=0)
    removed_submissions = IntegerField(default=0)
    approved_comments = IntegerField(default=0)
    approved_submissions = IntegerField(default=0)
    bans = IntegerField(default=0)
    shadowbanned = BooleanField(default=False)
    tracked = BooleanField(default=False)
    warnings_muted = BooleanField(default=False)
    last_warned = TimestampField(default=0, null=True)
    subreddit = TextField()


class SubmissionModel(BaseModel):
    submission_id = TextField()
    sticky_cmt_id = TextField(null=True)
    lock_type = TextField(null=True)
    lock_remaining = TimestampField(default=0)
    remove_remaining = TimestampField(default=0)
    subreddit = TextField()


class UnflairedSubmissionModel(BaseModel):
    submission_id = TextField()
    comment_id = TextField()
    subreddit = TextField()


class FilterModel(BaseModel):
    filter_string = TextField()
    subreddit = TextField()
    use_regex = BooleanField(default=False)
    expires = TimestampField(default=0)


class AlreadyDoneModel(BaseModel):
    thing_id = TextField(unique=True)
    timestamp = TimestampField()
    subreddit = TextField()
