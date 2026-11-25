from contextlib import contextmanager
from pathlib import Path
import json
import secrets
import sqlite3

from .bank import CONCEPTS, DIAGNOSTIC, PRACTICE, PREREQUISITES, grade


class StaleAction(ValueError):
    pass


class Store:
    def __init__(self, path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.transaction() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS learners (
                    id TEXT PRIMARY KEY, recommendation TEXT,
                    current TEXT, position INTEGER NOT NULL DEFAULT 0,
                    revision INTEGER NOT NULL DEFAULT 0
                );
                CREATE TABLE IF NOT EXISTS attempts (
                    id INTEGER PRIMARY KEY, learner TEXT NOT NULL REFERENCES learners(id),
                    problem TEXT NOT NULL, concept TEXT NOT NULL, phase TEXT NOT NULL,
                    answer TEXT NOT NULL, correct INTEGER NOT NULL,
                    position INTEGER NOT NULL, created TEXT DEFAULT CURRENT_TIMESTAMP
                );
                CREATE TABLE IF NOT EXISTS hints (
                    id INTEGER PRIMARY KEY, learner TEXT NOT NULL REFERENCES learners(id),
                    problem TEXT NOT NULL, position INTEGER NOT NULL
                );
                CREATE TABLE IF NOT EXISTS mastery (
                    learner TEXT NOT NULL REFERENCES learners(id), concept TEXT NOT NULL,
                    correct INTEGER NOT NULL, total INTEGER NOT NULL,
                    PRIMARY KEY(learner, concept)
                );
                CREATE TABLE IF NOT EXISTS logs (
                    id INTEGER PRIMARY KEY, learner TEXT NOT NULL REFERENCES learners(id),
                    payload TEXT NOT NULL
                );
            """)

    @contextmanager
    def transaction(self):
        db = sqlite3.connect(self.path, timeout=5)
        db.row_factory = sqlite3.Row
        try:
            db.execute("PRAGMA foreign_keys = ON")
            db.execute("BEGIN IMMEDIATE")
            with db:
                yield db
        finally:
            db.close()

    def create(self):
        learner = secrets.token_hex(16)
        with self.transaction() as db:
            db.execute("INSERT INTO learners(id) VALUES (?)", (learner,))
        return learner

    def exists(self, learner):
        with self.transaction() as db:
            return db.execute("SELECT 1 FROM learners WHERE id=?", (learner,)).fetchone() is not None

    @staticmethod
    def _state(db, learner):
        row = db.execute("SELECT * FROM learners WHERE id=?", (learner,)).fetchone()
        if row is None:
            raise ValueError("학습 코드를 확인해 주세요.")
        counts = {r["concept"]: (r["correct"], r["total"]) for r in db.execute(
            "SELECT * FROM mastery WHERE learner=?", (learner,)
        )}
        diagnostic = db.execute(
            "SELECT COUNT(*) FROM attempts WHERE learner=? AND phase='diagnostic'", (learner,)
        ).fetchone()[0]
        failures = db.execute(
            "SELECT COUNT(*) FROM attempts WHERE learner=? AND position=? AND correct=0",
            (learner, row["position"]),
        ).fetchone()[0]
        return {
            **dict(row), "diagnostic": diagnostic, "failures": failures,
            "mastery": {concept: counts.get(concept, (0, 0)) for concept in CONCEPTS},
        }

    def state(self, learner):
        with self.transaction() as db:
            return self._state(db, learner)

    @staticmethod
    def _recommend(mastery, previous=None):
        scores = {concept: correct / total if total else -1
                  for concept, (correct, total) in mastery.items()}
        weakest = min(CONCEPTS, key=scores.__getitem__)
        if previous is not None and scores[weakest] >= .8:
            concepts = tuple(CONCEPTS)
            return concepts[(concepts.index(previous) + 1) % len(concepts)]
        return weakest

    @staticmethod
    def _practice(concept, previous=None):
        return next(p.id for p in PRACTICE if p.concept == concept and p.id != previous)

    def submit(self, learner, problem, answer, revision, phase):
        correct = grade(problem, answer)
        with self.transaction() as db:
            state = self._state(db, learner)
            diagnostic = state["diagnostic"]
            expected_phase = "diagnostic" if diagnostic < len(DIAGNOSTIC) else "practice"
            expected = DIAGNOSTIC[diagnostic].id if expected_phase == "diagnostic" else state["current"]
            if (revision, phase, problem.id) != (state["revision"], expected_phase, expected):
                raise StaleAction("다른 화면에서 먼저 제출했어요. 새로고침해 주세요.")
            db.execute(
                "INSERT INTO attempts(learner,problem,concept,phase,answer,correct,position)"
                " VALUES (?,?,?,?,?,?,?)",
                (learner, problem.id, problem.concept, phase, answer.strip(), correct, state["position"]),
            )
            db.execute(
                "INSERT INTO mastery VALUES (?,?,?,1) ON CONFLICT(learner,concept)"
                " DO UPDATE SET correct=correct+excluded.correct,total=total+1",
                (learner, problem.concept, int(correct)),
            )
            state_after = self._state(db, learner)
            recommendation = state["recommendation"]
            current = state["current"]
            position = state["position"]
            action = "retry"
            if phase == "diagnostic":
                position += 1
                action = "diagnostic_next"
                if state_after["diagnostic"] == len(DIAGNOSTIC):
                    recommendation = self._recommend(state_after["mastery"])
                    current = self._practice(recommendation)
                    action = "diagnostic_done"
            elif correct:
                recommendation = self._recommend(state_after["mastery"], problem.concept)
                current = self._practice(recommendation, problem.id)
                position += 1
                action = "advance"
            elif state_after["failures"] >= 2:
                recommendation = PREREQUISITES.get(problem.concept, problem.concept)
                current = self._practice(recommendation, problem.id)
                position += 1
                action = "prerequisite" if recommendation != problem.concept else "review"
            else:
                db.execute("INSERT INTO hints(learner,problem,position) VALUES (?,?,?)",
                           (learner, problem.id, position))
            db.execute(
                "UPDATE learners SET recommendation=?,current=?,position=?,revision=revision+1 WHERE id=?",
                (recommendation, current, position, learner),
            )
        return {"correct": correct, "action": action, "recommendation": recommendation}

    def add_hint(self, learner, problem, position, current_required=False):
        with self.transaction() as db:
            if current_required:
                state = self._state(db, learner)
                if state["current"] != problem.id or state["position"] != position:
                    raise StaleAction("현재 문제를 다시 열어 주세요.")
            db.execute("INSERT INTO hints(learner,problem,position) VALUES (?,?,?)",
                       (learner, problem.id, position))

    def history(self, learner):
        with self.transaction() as db:
            return {
                "attempts": [dict(row) for row in db.execute(
                    "SELECT * FROM attempts WHERE learner=? ORDER BY id", (learner,)
                )],
                "hints": db.execute("SELECT COUNT(*) FROM hints WHERE learner=?", (learner,)).fetchone()[0],
                "logs": [json.loads(row[0]) for row in db.execute(
                    "SELECT payload FROM logs WHERE learner=? ORDER BY id DESC LIMIT 20", (learner,)
                )],
            }

    def save_log(self, learner, log):
        with self.transaction() as db:
            db.execute("INSERT INTO logs(learner,payload) VALUES (?,?)",
                       (learner, json.dumps(log, ensure_ascii=False)))
