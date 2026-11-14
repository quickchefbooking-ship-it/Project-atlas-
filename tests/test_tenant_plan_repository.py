import sqlite3
import pytest
from atlas_engine.identity_policy import AuthorizationDenied,RequestPrincipal
from atlas_engine.plan_contract import PlanState,PlanStep,ProfessorPlan,RiskClass
from atlas_engine.tenant_plan_repository import TenantPlanConflict,TenantPlanNotFound,TenantPlanRepository,initialize_tenant_plan_schema

@pytest.fixture
def repos():
 db=sqlite3.connect(":memory:"); db.row_factory=sqlite3.Row; initialize_tenant_plan_schema(db)
 a=RequestPrincipal("issuer","alice","tenant-a",True,frozenset({"plans:read","plans:write"}))
 b=RequestPrincipal("issuer","bob","tenant-b",True,frozenset({"plans:read","plans:write"}))
 return db,TenantPlanRepository(db,a),TenantPlanRepository(db,b)

def make_plan(pid="plan-a"):
 return ProfessorPlan(pid,"Research the question",("Use approved sources",),(
  PlanStep("search","knowledge.search","Find evidence",RiskClass.READ_ONLY,capability_version="2"),
  PlanStep("summarise","knowledge.summarise","Summarise evidence",RiskClass.LOCAL_COMPUTATION,depends_on=("search",))))

def test_create_steps_and_actor_history(repos):
 _,a,_=repos; p=make_plan(); assert a.create(p)==p and a.get(p.plan_id)==p
 assert [s["step_id"] for s in a.list_steps(p.plan_id)]==["search","summarise"]
 assert a.list_transitions(p.plan_id)[0].actor_subject=="alice"

def test_cross_tenant_read_list_step_and_transition_denied(repos):
 _,a,b=repos; b.create(make_plan()); assert a.list()==()
 with pytest.raises(TenantPlanNotFound): a.get("plan-a")
 with pytest.raises(TenantPlanNotFound): a.list_steps("plan-a")
 with pytest.raises(TenantPlanNotFound): a.transition("plan-a",expected_state=PlanState.DRAFT,new_state=PlanState.READY)

def test_same_plan_id_can_exist_in_two_tenants(repos):
 _,a,b=repos; a.create(make_plan("same")); b.create(make_plan("same")); assert a.get("same")==b.get("same")

def test_compare_and_swap_transition(repos):
 _,a,_=repos; a.create(make_plan())
 assert a.transition("plan-a",expected_state=PlanState.DRAFT,new_state=PlanState.READY).state is PlanState.READY
 with pytest.raises(TenantPlanConflict): a.transition("plan-a",expected_state=PlanState.DRAFT,new_state=PlanState.READY)

def test_approval_transition_unavailable(repos):
 _,a,_=repos; a.create(make_plan())
 with pytest.raises(TenantPlanConflict): a.transition("plan-a",expected_state=PlanState.DRAFT,new_state=PlanState.APPROVED)

def test_scopes_and_active_membership_required(repos):
 db,_,_=repos; reader=TenantPlanRepository(db,RequestPrincipal("issuer","reader","tenant-a",True,frozenset({"plans:read"})))
 with pytest.raises(AuthorizationDenied): reader.create(make_plan())
 inactive=TenantPlanRepository(db,RequestPrincipal("issuer","alice","tenant-a",False,frozenset({"plans:read"})))
 with pytest.raises(AuthorizationDenied): inactive.list()

def test_composite_foreign_key_blocks_cross_tenant_step(repos):
 db,a,_=repos; a.create(make_plan())
 with pytest.raises(sqlite3.IntegrityError):
  db.execute("""INSERT INTO tenant_professor_plan_steps(tenant_id,plan_id,step_id,ordinal,capability,risk)
   VALUES('tenant-b','plan-a','forged',0,'evil','read_only')""")
