import math
from collections import Counter

class BM25:
    def __init__(self, k1=1.5, b=0.75):
        self.k1 = k1
        self.b = b
        self.corpus_size = 0
        self.avgdl = 0
        self.doc_freqs = []
        self.idf = {}
        self.doc_len = []

    def fit(self, corpus):
        self.corpus_size = len(corpus)
        nd = {}
        num_doc = 0
        for document in corpus:
            self.doc_len.append(len(document))
            num_doc += len(document)
            frequencies = Counter(document)
            self.doc_freqs.append(frequencies)
            for word, freq in frequencies.items():
                nd[word] = nd.get(word, 0) + 1

        self.avgdl = num_doc / self.corpus_size if self.corpus_size > 0 else 0

        for word, freq in nd.items():
            self.idf[word] = math.log(((self.corpus_size - freq + 0.5) / (freq + 0.5)) + 1)

    def get_scores(self, query):
        scores = [0] * self.corpus_size
        for q in query:
            q_freq = self.idf.get(q, 0)
            if q_freq == 0:
                continue
            for i in range(self.corpus_size):
                f = self.doc_freqs[i].get(q, 0)
                if f == 0:
                    continue
                score = (self.idf[q] * f * (self.k1 + 1)) / (f + self.k1 * (1 - self.b + self.b * self.doc_len[i] / self.avgdl))
                scores[i] += score
        return scores
