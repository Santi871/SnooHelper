from flask_wtf import Form
from wtforms import SelectField, SelectMultipleField, widgets


class SubredditSelectForm(Form):
    subreddit_select = SelectField('selectsubreddit', choices=[])


class MultiCheckboxField(SelectMultipleField):
    widget = widgets.ListWidget(prefix_label=False)
    option_widget = widgets.CheckboxInput()


class ModulesSelectForm(Form):
    choices = [("usernotes", "Usernotes (requires 'modwiki' permission)"),
               ("usertracking", "User offense tracker (requires 'modlog' permission)")]
    modules_select = MultiCheckboxField('Select modules', choices=choices)
