import re
from abc import ABC, abstractmethod
from collections import Counter


class BaseTokenizer(ABC):
    name = "base"

    @abstractmethod
    def tokenize(self, text: str) -> Counter:
        raise NotImplementedError


class RegexTokenizer(BaseTokenizer):
    name = "regex"

    def tokenize(self, text: str) -> Counter:
        candidates = Counter()
        for chunk in re.findall(r"[\u4e00-\u9fff]+", text):
            limit = min(len(chunk), 6)
            for size in range(2, limit + 1):
                candidates.update(
                    chunk[index:index + size]
                    for index in range(len(chunk) - size + 1)
                )
        candidates.update(re.findall(r"[A-Za-z_][A-Za-z0-9_]{1,}", text))
        return candidates
