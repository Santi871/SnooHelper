import datetime
import stop_words
import json


class AnalysisResults:

    def __init__(self, user, num_submissions, domains, titles, copied_titles, frequency, time, num_comments=None):
        self.user = user
        self.num_submissions = num_submissions
        self.domains = domains
        self.domain_ratios = self.domains.get('ratios', list())
        self.submitted_from = self.domains.get('submitted_from', list())
        self.titles = titles
        self.copied_titles = copied_titles
        self.frequency = frequency
        self.time = time
        self.num_comments = num_comments
        self.account_creation = datetime.datetime.fromtimestamp(user.created_utc)
        self.combined_karma = user.link_karma + user.comment_karma
        self.spammer_likelihood = self._calculate_spammer_likelihood()

    def _calculate_spammer_likelihood(self):

        spammer_likelihood = 0
        shadowbanned_users = 0

        if self.num_submissions < 3 or self.user.is_gold:
            return 0

        for _, val in self.domain_ratios.items():
            spammer_likelihood += 5
            shadowbanned_users += val[1]

        for dom, val in self.submitted_from.items():
            if self.user.name in dom or dom in self.user.name:
                spammer_likelihood += 100

            if val > 0.6 and self.combined_karma < 5000 and \
                    self.account_creation < datetime.datetime.utcnow() - datetime.timedelta(days=90):
                spammer_likelihood += 50
            elif val > 0.9 and self.combined_karma < 10000:
                spammer_likelihood += 100

        for freq in self.frequency:
            if freq > 6 and self.combined_karma < 20000:
                spammer_likelihood += 50

        if self.copied_titles > 2 and self.combined_karma < 50000:
            spammer_likelihood += 50

        for tup in self.titles:
            if tup[1] > 20:
                spammer_likelihood += 25

        if self.combined_karma < 1000:
            spammer_likelihood += 25
        elif 1000 < self.combined_karma < 5000:
            spammer_likelihood += 10
        elif self.combined_karma > 10000:
            spammer_likelihood -= 30
        elif self.combined_karma > 50000:
            spammer_likelihood -= 70
        elif self.combined_karma > 120000:
            spammer_likelihood -= 100

        if self.account_creation > datetime.datetime.utcnow() - datetime.timedelta(days=30):
            spammer_likelihood += 50

        if self.account_creation < datetime.datetime.utcnow() - datetime.timedelta(days=300):
            spammer_likelihood -= 50

        if self.num_comments is not None:
            if self.num_comments > 20 and self.account_creation < datetime.datetime.utcnow() - \
                    datetime.timedelta(days=90):
                spammer_likelihood -= 50

        spammer_likelihood = max(min(spammer_likelihood, 500), 0)

        return spammer_likelihood

    def get_dict(self):
        retdict = {
            'user': self.user.name,
            'num_submissions': self.num_submissions,
            'num_comments': self.num_comments,
            'domains': self.domains,
            'titles': self.titles,
            'copied_titles': self.copied_titles,
            'frequency': self.frequency,
            'time': self.time,
            'account_creation': self.user.created_utc,
            'combined_karma': self.combined_karma,
            'is_gilded': self.user.is_gold,
            'spammer_likelihood': self.spammer_likelihood,
        }

        return retdict

    def get_json(self, indent=0):
        return json.dumps(self.get_dict(), indent=indent)


class UserAnalyzer:

    def __init__(self, r, config):
        self.r = r
        self.config = config
        self.stopwords = stop_words.get_stop_words('en')

    def analyze_user(self, name, get_comments=False, submissions_limit=50, verbose=False):
        start = datetime.datetime.now()
        if verbose:
            print("Analyzing user: " + name)

        submissions, user, num_comments = self.get_user_details(name, get_comments, limit=submissions_limit)
        analyzed_domains = self.analyze_user_domains(name, submissions)
        analyzed_titles, copied_titles = self.analyze_submission_titles(submissions)
        submission_frequency = self.analyze_submission_frequency(submissions)

        timedelta = datetime.datetime.now() - start
        elapsed = round(timedelta.total_seconds(), 1)

        if verbose:
            print("Done... took %s seconds" % elapsed)

        retval = AnalysisResults(user, len(submissions), analyzed_domains, analyzed_titles, copied_titles,
                                 submission_frequency, elapsed, num_comments)

        return retval

    @staticmethod
    def consolidate_domain(domain):

        if domain == 'i.imgur.com' or 'm.imgur.com':
            return 'imgur.com'
        elif domain == 'youtu.be' or domain == 'm.youtube.com':
            return 'youtube.com'
        else:
            return domain

    def get_user_details(self, username, get_comments=False, limit=50):

        user = self.r.get_redditor(username)
        submissions = [submission for submission in
                       user.get_submitted(sort='new', time='year', limit=limit) if not submission.is_self]

        if get_comments:
            num_comments = len(list(user.get_comments(limit=30)))
        else:
            num_comments = None

        return submissions, user, num_comments

    def analyze_user_domains(self, username, submissions, domain_submissions_limit=100, verbose=False):

        submission_domains = dict()
        domain_ratios = dict()
        domains_submitted_from = dict()
        total_domains = 0
        total_submissions = len(submissions)
        whitelist = self.config.get_domain_whitelist()

        for submission in submissions:
            domain = self.consolidate_domain(submission.domain)
            domain_count = submission_domains.get(domain, 0)
            if not domain_count:
                total_domains += 1

            domain_count += 1
            submission_domains[domain] = domain_count

        for domain in list(submission_domains.keys())[:7]:
            if domain not in whitelist:

                total_read_domains = 0
                username_submitted_domains = 0
                shadowbanned_users = 0

                if verbose:
                    print("Analyzing domain: " + domain)
                domain_listing = list(self.r.get_domain_listing(domain, limit=domain_submissions_limit))
                for submission in domain_listing:
                    total_read_domains += 1

                    try:
                        if submission.author.name == username:
                            username_submitted_domains += 1
                    except AttributeError:
                        shadowbanned_users += 1
                try:
                    ratio = round(username_submitted_domains / total_read_domains, 2)

                    if ratio >= 0.1:
                        domain_ratios[domain] = (ratio, shadowbanned_users)
                    else:
                        self.config.add_whitelisted_domain(domain)
                except ZeroDivisionError:
                    pass

            domains_submitted_from[domain] = round(submission_domains[domain] / total_submissions, 2)

        return {'ratios': domain_ratios, 'submitted_from': domains_submitted_from}

    def analyze_submission_titles(self, submissions, min_count=1):
        joined_titles = ""
        wordfreq = list()
        already_done_words = list()
        last_title = None
        copied_titles = 0

        for submission in submissions:
            if last_title is not None and last_title in submission.title:
                copied_titles += 1

            split_title = submission.title.lower().split()
            filtered_title = ' '.join([word for word in split_title if word not in self.stopwords])
            joined_titles += filtered_title
            last_title = submission.title

        for w in joined_titles.split():
            count = joined_titles.count(w)
            if w not in already_done_words and count > min_count and len(w) > 1:
                already_done_words.append(w)
                wordfreq.append((w, joined_titles.count(w)))

        wordfreq = sorted(wordfreq, key=lambda tup: tup[1], reverse=True)

        return wordfreq, copied_titles

    @staticmethod
    def analyze_submission_frequency(submissions):
        i = 0
        submission_count_by_day = list()

        while i < len(submissions):
            start_date = datetime.datetime.fromtimestamp(submissions[i].created_utc)
            end_date = start_date - datetime.timedelta(days=1)
            todays_submissions = 0

            for submission in submissions[i:]:
                sdt = datetime.datetime.fromtimestamp(submission.created_utc)
                i += 1
                if end_date < sdt <= start_date:
                    todays_submissions += 1
                elif sdt < end_date:
                    break

            submission_count_by_day.append(todays_submissions)

        return submission_count_by_day
