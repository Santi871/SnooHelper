from flask_wtf import Form
from wtforms import SelectField


class SubredditSelectForm(Form):
    subreddit_select = SelectField('selectsubreddit', choices=[])
