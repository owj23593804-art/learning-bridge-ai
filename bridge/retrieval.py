from collections import Counter
from dataclasses import dataclass
from math import log, sqrt
from pathlib import Path
import re

from .bank import CONCEPTS


@dataclass(frozen=True)
class Chunk:
    id: str
    source: str
    concept: str
    text: str


class MaterialIndex:
    def __init__(self, directory, model_path=None):
        self.chunks = []
        self.warnings = []
        for path in sorted(Path(directory).glob("*")):
            if path.suffix.lower() == ".md":
                try:
                    self._add_text(path.name, path.read_text(encoding="utf-8"))
                except (OSError, UnicodeError):
                    self.warnings.append("읽을 수 없는 Markdown 자료를 건너뛰었어요.")
            elif path.suffix.lower() == ".pdf":
                try:
                    import pymupdf

                    with pymupdf.open(path) as document:
                        for page in document:
                            self._add_text(f"{path.name} · {page.number + 1}쪽", page.get_text())
                except (ImportError, RuntimeError, OSError, ValueError):
                    self.warnings.append("읽을 수 없는 PDF를 건너뛰었어요.")
        self.model = None
        self.vectors = None
        frequencies = Counter(term for chunk in self.chunks for term in set(self._terms(chunk.text)))
        self.weights = {term: 1 + log((1 + len(self.chunks)) / (1 + count))
                        for term, count in frequencies.items()}
        self.lexical_vectors = [self._vector(chunk.text) for chunk in self.chunks]
        if model_path and self.chunks:
            try:
                from sentence_transformers import SentenceTransformer

                model = SentenceTransformer(str(model_path), local_files_only=True, device="cpu")
                self.vectors = model.encode(
                    [chunk.text for chunk in self.chunks], normalize_embeddings=True
                )
                self.model = model
            except (ImportError, OSError, RuntimeError, ValueError):
                self.warnings.append("임베딩 모델을 열지 못해 기본 검색을 사용해요.")

    def _add_text(self, source, text):
        pattern = r"(?m)^\[(\w+)\]\s*$"
        sections = re.split(pattern, text)
        for index in range(1, len(sections), 2):
            concept = sections[index]
            if concept not in CONCEPTS:
                continue
            body = " ".join(sections[index + 1].split())
            for offset in range(0, len(body), 400):
                fragment = body[offset:offset + 440]
                self.chunks.append(Chunk(f"m{len(self.chunks) + 1}", source, concept, fragment))

    @staticmethod
    def _terms(text):
        for word in re.findall(r"[가-힣A-Za-z0-9]+", text.lower()):
            yield from (word[i:i + 2] for i in range(max(1, len(word) - 1)))

    def _vector(self, text):
        entries = {term: count * self.weights[term] for term, count in Counter(self._terms(text)).items()
                   if term in self.weights}
        norm = sqrt(sum(value ** 2 for value in entries.values())) or 1
        return {term: value / norm for term, value in entries.items()}

    def search(self, concept, question=""):
        matching = [(index, chunk) for index, chunk in enumerate(self.chunks) if chunk.concept == concept]
        if not matching:
            return []
        query = f"{CONCEPTS[concept]} {question}"
        if self.model is not None:
            try:
                vector = self.model.encode(query, normalize_embeddings=True)
                matching.sort(key=lambda item: float(self.vectors[item[0]] @ vector), reverse=True)
                return [chunk for _, chunk in matching[:3]]
            except (OSError, RuntimeError, ValueError):
                pass
        vector = self._vector(query)
        matching.sort(key=lambda item: sum(value * self.lexical_vectors[item[0]].get(term, 0)
                                           for term, value in vector.items()), reverse=True)
        return [chunk for _, chunk in matching[:3]]
