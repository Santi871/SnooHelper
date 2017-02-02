from collections import Counter
from wordcloud import STOPWORDS
from textblob import TextBlob


def intersect(lists):
    ret_set = set(lists[0])

    for index, element in enumerate(lists):
        if index > 0:
            ret_set = ret_set & set(element)

    ret_list = list(ret_set)
    return ret_list, Counter(ret_list)


class Floodgate:

    def __init__(self, max_delta_hours=5, most_common_threshold=5, faq_term_count_threshold=4):
        self.titles_accumulator = list()
        self.max_delta_hours = max_delta_hours
        self.most_common_threshold = most_common_threshold
        self.faq_term_count_threshold = faq_term_count_threshold

    def accumulate_title(self, title, created_timestamp):
        title_words = TextBlob(title).words
        t = (title_words, created_timestamp)
        self.titles_accumulator.append(t)
        return t

    def check_all(self):

        delta_hours = 0
        i = 0
        titles_to_intersect = list()
        faq_terms = list()
        titles_acc_len = len(self.titles_accumulator)

        if titles_acc_len < 3:
            return None

        while delta_hours <= self.max_delta_hours and i < titles_acc_len:
            delta_hours = (self.titles_accumulator[i][1] - self.titles_accumulator[i+1][1]) / 3600
            titles_to_intersect.append(self.titles_accumulator[i])
            i += 1

        results_list, results_counter = intersect(titles_to_intersect)
        most_common_terms = results_counter.most_common(self.most_common_threshold)

        for tup in most_common_terms:
            if tup[1] >= self.faq_term_count_threshold:
                faq_terms.append(tup[0])

        print(str(self.titles_accumulator))
        print(str(results_counter))

        if faq_terms:
            print(str(faq_terms))
            return faq_terms
        return None


