import uuid

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.chaos import runner
from app.db import get_db
from app.schemas.experiments import ExperimentCreate, ExperimentRecord

router = APIRouter(prefix="/experiments", tags=["experiments"])


@router.post("", response_model=ExperimentRecord, status_code=201)
def start_experiment(body: ExperimentCreate, db: Session = Depends(get_db)) -> ExperimentRecord:
    return runner.start_experiment(db, body)


@router.post("/{experiment_id}/clear", response_model=ExperimentRecord)
def clear_experiment(experiment_id: uuid.UUID, db: Session = Depends(get_db)) -> ExperimentRecord:
    return runner.clear_experiment(db, experiment_id)