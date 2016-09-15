from flask_wtf import Form
from wtforms import SelectField

choices = [('choice1', 'Choice1'), ('choice2', 'Choice2')]


class SubredditSelectForm(Form):
    subreddit_select = SelectField('selectsubreddit', choices=[])