"""Tenant-local, human-authored lesson review; approved entries are not executable memory."""
from __future__ import annotations
import hashlib, json, sqlite3
from dataclasses import dataclass
from .identity_policy import RequestPrincipal, authorize_tenant_resource

def initialize_tenant_lesson_review_schema(db: sqlite3.Connection) -> None:
    db.executescript("""
    CREATE TABLE IF NOT EXISTS tenant_lesson_candidates (
      candidate_id INTEGER PRIMARY KEY AUTOINCREMENT,
      tenant_id TEXT NOT NULL, owner_key TEXT NOT NULL, proposer_key TEXT NOT NULL,
      title TEXT NOT NULL, lesson_text TEXT NOT NULL, evaluation_ids_json TEXT NOT NULL,
      created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
    );
    CREATE TABLE IF NOT EXISTS tenant_lesson_candidate_decisions (
      decision_id INTEGER PRIMARY KEY AUTOINCREMENT, candidate_id INTEGER NOT NULL,
      tenant_id TEXT NOT NULL, owner_key TEXT NOT NULL, reviewer_key TEXT NOT NULL,
      decision TEXT NOT NULL CHECK(decision IN ('approved','rejected')),
      rationale TEXT NOT NULL, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
      FOREIGN KEY(candidate_id) REFERENCES tenant_lesson_candidates(candidate_id)
    );
    CREATE INDEX IF NOT EXISTS idx_lesson_candidates_owner ON tenant_lesson_candidates(tenant_id,owner_key,candidate_id DESC);
    CREATE INDEX IF NOT EXISTS idx_lesson_decisions_candidate ON tenant_lesson_candidate_decisions(candidate_id,decision_id DESC);
    CREATE UNIQUE INDEX IF NOT EXISTS idx_lesson_single_final_decision ON tenant_lesson_candidate_decisions(candidate_id);
    CREATE TRIGGER IF NOT EXISTS lesson_candidates_no_update BEFORE UPDATE ON tenant_lesson_candidates BEGIN SELECT RAISE(ABORT,'lesson candidates are immutable'); END;
    CREATE TRIGGER IF NOT EXISTS lesson_candidates_no_delete BEFORE DELETE ON tenant_lesson_candidates BEGIN SELECT RAISE(ABORT,'lesson candidates are immutable'); END;
    CREATE TRIGGER IF NOT EXISTS lesson_decisions_no_update BEFORE UPDATE ON tenant_lesson_candidate_decisions BEGIN SELECT RAISE(ABORT,'lesson decisions are append-only'); END;
    CREATE TRIGGER IF NOT EXISTS lesson_decisions_no_delete BEFORE DELETE ON tenant_lesson_candidate_decisions BEGIN SELECT RAISE(ABORT,'lesson decisions are append-only'); END;
    """)

class TenantLessonReviewRepository:
    def __init__(self, db: sqlite3.Connection, principal: RequestPrincipal):
        if not isinstance(principal, RequestPrincipal): raise TypeError("Verified principal required.")
        self.db, self.p = db, principal
        self.db.row_factory = sqlite3.Row
        self.key = hashlib.sha256((principal.issuer+"\0"+principal.subject).encode()).hexdigest()
    def _auth(self, scope): authorize_tenant_resource(self.p,self.p.tenant_id,{scope})
    def propose(self, *, title, lesson_text, evaluation_ids):
        self._auth("lessons:propose")
        if not isinstance(title,str) or not title.strip() or len(title)>160: raise ValueError("title must be 1-160 characters.")
        if not isinstance(lesson_text,str) or not lesson_text.strip() or len(lesson_text)>2000: raise ValueError("lesson_text must be 1-2000 characters.")
        if not isinstance(evaluation_ids,list) or not 1<=len(evaluation_ids)<=20 or any(type(x) is not int or x<=0 for x in evaluation_ids) or len(set(evaluation_ids))!=len(evaluation_ids): raise ValueError("Provide 1-20 unique positive evaluation IDs.")
        placeholders=",".join("?" for _ in evaluation_ids)
        rows=self.db.execute(f"SELECT evaluation_id FROM tenant_professor_evaluations WHERE tenant_id=? AND owner_key=? AND evaluation_id IN ({placeholders})",(self.p.tenant_id,self.key,*evaluation_ids)).fetchall()
        if {r["evaluation_id"] for r in rows}!=set(evaluation_ids): raise LookupError("One or more evaluations were not found.")
        with self.db:
            cur=self.db.execute("INSERT INTO tenant_lesson_candidates(tenant_id,owner_key,proposer_key,title,lesson_text,evaluation_ids_json) VALUES(?,?,?,?,?,?)",(self.p.tenant_id,self.key,self.key,title.strip(),lesson_text.strip(),json.dumps(sorted(evaluation_ids))))
        return cur.lastrowid
    def decide(self, candidate_id, *, decision, rationale=""):
        self._auth("lessons:approve")
        if decision not in {"approved","rejected"}: raise ValueError("Decision must be approved or rejected.")
        if not isinstance(rationale,str) or len(rationale)>1000: raise ValueError("Rationale must be at most 1000 characters.")
        row=self.db.execute("SELECT * FROM tenant_lesson_candidates WHERE candidate_id=? AND tenant_id=?",(candidate_id,self.p.tenant_id)).fetchone()
        if row is None: raise LookupError("Lesson candidate not found.")
        if row["proposer_key"]==self.key: raise PermissionError("A different reviewer must decide this proposal.")
        latest=self.db.execute("SELECT decision FROM tenant_lesson_candidate_decisions WHERE candidate_id=? ORDER BY decision_id DESC LIMIT 1",(candidate_id,)).fetchone()
        if latest: raise ValueError("This candidate already has a final review decision.")
        with self.db:
            self.db.execute("INSERT INTO tenant_lesson_candidate_decisions(candidate_id,tenant_id,owner_key,reviewer_key,decision,rationale) VALUES(?,?,?,?,?,?)",(candidate_id,self.p.tenant_id,self.key,self.key,decision,rationale.strip()))
        return decision
    def approved_owned_candidate(self, candidate_id):
        """Return an independently approved lesson owned by this principal."""
        self._auth("lessons:read")
        row = self.db.execute(
            """SELECT candidate_id,title,lesson_text FROM tenant_lesson_candidates
               WHERE candidate_id=? AND tenant_id=? AND owner_key=?""",
            (candidate_id, self.p.tenant_id, self.key),
        ).fetchone()
        if row is None:
            raise LookupError("Approved lesson candidate not found.")
        decision = self.db.execute(
            """SELECT decision,reviewer_key FROM tenant_lesson_candidate_decisions
               WHERE candidate_id=? AND tenant_id=?
               ORDER BY decision_id DESC LIMIT 1""",
            (candidate_id, self.p.tenant_id),
        ).fetchone()
        if decision is None or decision["decision"] != "approved":
            raise ValueError("Only approved lesson candidates can be converted to memory proposals.")
        if decision["reviewer_key"] == self.key:
            raise PermissionError("Lesson approval must come from an independent reviewer.")
        return dict(row)

    def list(self, limit=50):
        self._auth("lessons:read")
        if type(limit) is not int or not 1<=limit<=100: raise ValueError("limit must be 1-100.")
        rows=self.db.execute("""SELECT c.*, (SELECT d.decision FROM tenant_lesson_candidate_decisions d WHERE d.candidate_id=c.candidate_id ORDER BY d.decision_id DESC LIMIT 1) AS status FROM tenant_lesson_candidates c WHERE c.tenant_id=? ORDER BY c.candidate_id DESC LIMIT ?""",(self.p.tenant_id,limit)).fetchall()
        return [{"candidate_id":r["candidate_id"],"title":r["title"],"lesson_text":r["lesson_text"],"evaluation_ids":json.loads(r["evaluation_ids_json"]),"status":r["status"] or "pending","created_at":r["created_at"],"runtime_promotion":"disabled"} for r in rows]
