"""Isolated tenant-scoped Professor plan and step metadata prototype."""
import sqlite3
from dataclasses import dataclass
from .identity_policy import RequestPrincipal, authorize_tenant_resource
from .plan_contract import PlanState, ProfessorPlan
from .plan_repository import _decode_plan, _encode_plan

class TenantPlanNotFound(LookupError): pass
class TenantPlanConflict(RuntimeError): pass

@dataclass(frozen=True)
class TenantPlanTransition:
    plan_id: str
    from_state: PlanState | None
    to_state: PlanState
    actor_issuer: str
    actor_subject: str
    created_at: str

def initialize_tenant_plan_schema(db: sqlite3.Connection) -> None:
    db.execute("PRAGMA foreign_keys=ON")
    db.executescript("""
    CREATE TABLE IF NOT EXISTS tenant_professor_plans(
      tenant_id TEXT NOT NULL, plan_id TEXT NOT NULL,
      state TEXT NOT NULL CHECK(state IN ('draft','ready','awaiting_approval','approved','running','succeeded','failed','cancelled')),
      plan_json TEXT NOT NULL, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
      updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP, PRIMARY KEY(tenant_id,plan_id));
    CREATE TABLE IF NOT EXISTS tenant_professor_plan_steps(
      tenant_id TEXT NOT NULL, plan_id TEXT NOT NULL, step_id TEXT NOT NULL,
      ordinal INTEGER NOT NULL CHECK(ordinal>=0), capability TEXT NOT NULL,
      capability_version TEXT, risk TEXT NOT NULL,
      PRIMARY KEY(tenant_id,plan_id,step_id), UNIQUE(tenant_id,plan_id,ordinal),
      FOREIGN KEY(tenant_id,plan_id) REFERENCES tenant_professor_plans(tenant_id,plan_id) ON DELETE RESTRICT);
    CREATE TABLE IF NOT EXISTS tenant_professor_plan_transitions(
      transition_id INTEGER PRIMARY KEY AUTOINCREMENT, tenant_id TEXT NOT NULL,
      plan_id TEXT NOT NULL, from_state TEXT, to_state TEXT NOT NULL,
      actor_issuer TEXT NOT NULL, actor_subject TEXT NOT NULL,
      created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
      FOREIGN KEY(tenant_id,plan_id) REFERENCES tenant_professor_plans(tenant_id,plan_id) ON DELETE RESTRICT);
    CREATE INDEX IF NOT EXISTS idx_tenant_professor_plans_state ON tenant_professor_plans(tenant_id,state,updated_at DESC);
    CREATE INDEX IF NOT EXISTS idx_tenant_professor_plan_transitions ON tenant_professor_plan_transitions(tenant_id,plan_id,transition_id);
    """)

class TenantPlanRepository:
    """Tenant-filtered plan metadata; approval and execution remain disabled."""
    def __init__(self, db: sqlite3.Connection, principal: RequestPrincipal):
        if not isinstance(db,sqlite3.Connection): raise TypeError("A caller-owned SQLite connection is required.")
        if not isinstance(principal,RequestPrincipal): raise TypeError("A verified RequestPrincipal is required.")
        self.db=db; self.db.execute("PRAGMA foreign_keys=ON"); self.principal=principal
    def _auth(self,scope):
        authorize_tenant_resource(self.principal,self.principal.tenant_id,{scope})
    def create(self,plan: ProfessorPlan):
        self._auth("plans:write")
        if not isinstance(plan,ProfessorPlan): raise TypeError("A validated ProfessorPlan is required.")
        if plan.state is not PlanState.DRAFT or plan.approval_reference is not None:
            raise TenantPlanConflict("New tenant plans must begin as unapproved drafts.")
        with self.db:
            self.db.execute("INSERT INTO tenant_professor_plans(tenant_id,plan_id,state,plan_json) VALUES(?,?,?,?)",
              (self.principal.tenant_id,plan.plan_id,plan.state.value,_encode_plan(plan)))
            self.db.executemany("""INSERT INTO tenant_professor_plan_steps
              (tenant_id,plan_id,step_id,ordinal,capability,capability_version,risk) VALUES(?,?,?,?,?,?,?)""",
              [(self.principal.tenant_id,plan.plan_id,s.step_id,i,s.capability,s.capability_version,s.risk.value) for i,s in enumerate(plan.steps)])
            self.db.execute("""INSERT INTO tenant_professor_plan_transitions
              (tenant_id,plan_id,from_state,to_state,actor_issuer,actor_subject) VALUES(?,?,NULL,?,?,?)""",
              (self.principal.tenant_id,plan.plan_id,plan.state.value,self.principal.issuer,self.principal.subject))
        return plan
    def get(self,plan_id):
        self._auth("plans:read")
        r=self.db.execute("SELECT plan_json FROM tenant_professor_plans WHERE tenant_id=? AND plan_id=?",
          (self.principal.tenant_id,plan_id)).fetchone()
        if r is None: raise TenantPlanNotFound("Plan was not found.")
        return _decode_plan(r["plan_json"])
    def list(self,*,state=None,limit=50):
        self._auth("plans:read")
        if isinstance(limit,bool) or not isinstance(limit,int) or not 1<=limit<=200: raise ValueError("limit must be between 1 and 200.")
        if state is not None and not isinstance(state,PlanState): raise TypeError("state must be a PlanState.")
        sql="SELECT plan_json FROM tenant_professor_plans WHERE tenant_id=?"; args=[self.principal.tenant_id]
        if state is not None: sql+=" AND state=?"; args.append(state.value)
        sql+=" ORDER BY created_at DESC,plan_id LIMIT ?"; args.append(limit)
        return tuple(_decode_plan(r["plan_json"]) for r in self.db.execute(sql,args).fetchall())
    def transition(self,plan_id,*,expected_state,new_state):
        self._auth("plans:write")
        if not isinstance(expected_state,PlanState) or not isinstance(new_state,PlanState): raise TypeError("PlanState values required.")
        allowed={PlanState.DRAFT:{PlanState.READY,PlanState.AWAITING_APPROVAL},PlanState.READY:{PlanState.RUNNING,PlanState.CANCELLED},PlanState.RUNNING:{PlanState.SUCCEEDED,PlanState.FAILED,PlanState.CANCELLED}}
        if new_state not in allowed.get(expected_state,set()): raise TenantPlanConflict("Tenant plan transition is not permitted.")
        with self.db:
            self.db.execute("BEGIN IMMEDIATE")
            r=self.db.execute("SELECT plan_json FROM tenant_professor_plans WHERE tenant_id=? AND plan_id=?",
              (self.principal.tenant_id,plan_id)).fetchone()
            if r is None: raise TenantPlanNotFound("Plan was not found.")
            old=_decode_plan(r["plan_json"])
            if old.state is not expected_state: raise TenantPlanConflict("Tenant plan state changed.")
            if new_state in {PlanState.SUCCEEDED, PlanState.FAILED}:
                cancellation_table = self.db.execute(
                    "SELECT 1 FROM sqlite_master WHERE type='table' AND name='tenant_professor_cancellation_requests'"
                ).fetchone()
                if cancellation_table is not None:
                    requested = self.db.execute(
                        "SELECT 1 FROM tenant_professor_cancellation_requests WHERE tenant_id=? AND plan_id=?",
                        (self.principal.tenant_id, plan_id),
                    ).fetchone()
                    if requested is not None:
                        raise TenantPlanConflict("A cancellation request prevents terminal plan completion.")
            new=ProfessorPlan(old.plan_id,old.objective,old.acceptance_criteria,old.steps,new_state,old.approval_reference)
            cur=self.db.execute("""UPDATE tenant_professor_plans SET state=?,plan_json=?,updated_at=CURRENT_TIMESTAMP
              WHERE tenant_id=? AND plan_id=? AND state=?""",
              (new_state.value,_encode_plan(new),self.principal.tenant_id,plan_id,expected_state.value))
            if cur.rowcount!=1: raise TenantPlanConflict("Tenant plan state changed concurrently.")
            self.db.execute("""INSERT INTO tenant_professor_plan_transitions
              (tenant_id,plan_id,from_state,to_state,actor_issuer,actor_subject) VALUES(?,?,?,?,?,?)""",
              (self.principal.tenant_id,plan_id,expected_state.value,new_state.value,self.principal.issuer,self.principal.subject))
        return new
    def list_steps(self,plan_id):
        self._auth("plans:read")
        if self.db.execute("SELECT 1 FROM tenant_professor_plans WHERE tenant_id=? AND plan_id=?",
          (self.principal.tenant_id,plan_id)).fetchone() is None: raise TenantPlanNotFound("Plan was not found.")
        return [dict(r) for r in self.db.execute("""SELECT step_id,ordinal,capability,capability_version,risk
          FROM tenant_professor_plan_steps WHERE tenant_id=? AND plan_id=? ORDER BY ordinal""",
          (self.principal.tenant_id,plan_id)).fetchall()]
    def list_transitions(self,plan_id):
        self._auth("plans:read")
        rows=self.db.execute("""SELECT t.plan_id,t.from_state,t.to_state,t.actor_issuer,t.actor_subject,t.created_at
          FROM tenant_professor_plan_transitions t JOIN tenant_professor_plans p
          ON p.tenant_id=t.tenant_id AND p.plan_id=t.plan_id
          WHERE t.tenant_id=? AND t.plan_id=? ORDER BY t.transition_id""",
          (self.principal.tenant_id,plan_id)).fetchall()
        if not rows: raise TenantPlanNotFound("Plan was not found.")
        return [TenantPlanTransition(r["plan_id"],PlanState(r["from_state"]) if r["from_state"] else None,
          PlanState(r["to_state"]),r["actor_issuer"],r["actor_subject"],r["created_at"]) for r in rows]
