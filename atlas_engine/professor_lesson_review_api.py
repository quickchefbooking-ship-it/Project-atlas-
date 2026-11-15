"""Authenticated tenant-local human lesson proposal and review routes."""
import sqlite3
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from .http_identity import require_verified_principal
from .tenant_lesson_review import TenantLessonReviewRepository

router=APIRouter()
class LessonProposalInput(BaseModel):
    model_config={"extra":"forbid"}
    title:str=Field(min_length=1,max_length=160)
    lesson_text:str=Field(min_length=1,max_length=2000)
    evaluation_ids:list[int]=Field(min_length=1,max_length=20)
class LessonDecisionInput(BaseModel):
    model_config={"extra":"forbid"}
    decision:str=Field(pattern="^(approved|rejected)$")
    rationale:str=Field(default="",max_length=1000)
def _repo(request,principal):
    path=getattr(request.app.state,"tenant_data_path",None)
    if not path: raise HTTPException(status_code=503,detail="Tenant lesson storage is not configured.")
    db=sqlite3.connect(path,timeout=5); db.row_factory=sqlite3.Row
    return db,TenantLessonReviewRepository(db,principal)
@router.post("/professor/tenant/lessons",status_code=201)
def propose_lesson(payload:LessonProposalInput,request:Request,principal=Depends(require_verified_principal)):
    db,repo=_repo(request,principal)
    try:
        candidate_id=repo.propose(title=payload.title,lesson_text=payload.lesson_text,evaluation_ids=payload.evaluation_ids)
        return {"candidate_id":candidate_id,"status":"pending","runtime_promotion":"disabled","message":"Human-authored proposal saved for independent review."}
    except PermissionError: raise HTTPException(403,detail="Lesson proposal access denied.") from None
    except LookupError: raise HTTPException(404,detail="One or more evaluations were not found.") from None
    except (ValueError,TypeError) as exc: raise HTTPException(422,detail=str(exc)) from None
    except sqlite3.Error: raise HTTPException(503,detail="Lesson review storage unavailable.") from None
    finally: db.close()
@router.get("/professor/tenant/lessons")
def list_lessons(request:Request,limit:int=50,principal=Depends(require_verified_principal)):
    db,repo=_repo(request,principal)
    try: return {"lessons":repo.list(limit)}
    except PermissionError: raise HTTPException(403,detail="Lesson review access denied.") from None
    except ValueError as exc: raise HTTPException(422,detail=str(exc)) from None
    except sqlite3.Error: raise HTTPException(503,detail="Lesson review storage unavailable.") from None
    finally: db.close()
@router.post("/professor/tenant/lessons/{candidate_id}/decision")
def decide_lesson(candidate_id:int,payload:LessonDecisionInput,request:Request,principal=Depends(require_verified_principal)):
    db,repo=_repo(request,principal)
    try:
        decision=repo.decide(candidate_id,decision=payload.decision,rationale=payload.rationale)
        return {"candidate_id":candidate_id,"status":decision,"runtime_promotion":"disabled","message":"Decision recorded; this does not add the lesson to execution memory."}
    except PermissionError as exc: raise HTTPException(403,detail=str(exc)) from None
    except LookupError: raise HTTPException(404,detail="Lesson candidate not found.") from None
    except ValueError as exc: raise HTTPException(409,detail=str(exc)) from None
    except sqlite3.Error: raise HTTPException(503,detail="Lesson review storage unavailable.") from None
    finally: db.close()
