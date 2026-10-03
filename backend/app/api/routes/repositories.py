from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_db
from app.core.config import settings
from app.models.repository import IndexStatus
from app.models.user import User
from app.repositories.project_repository import ProjectRepository
from app.repositories.repository_repository import RepositoryRepository
from app.schemas.repository import IndexTriggerResponse, RepositoryCreate, RepositoryOut
from app.utils.github_parser import validate_github_url
from app.workers.kafka_producer import publish_event

router = APIRouter(tags=["repositories"])


@router.post(
    "/projects/{project_id}/repositories",
    response_model=RepositoryOut,
    status_code=status.HTTP_201_CREATED,
)
async def connect_repository(
    project_id: UUID,
    payload: RepositoryCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    project = await ProjectRepository(db).get_owned(project_id, current_user.id)
    if project is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")

    try:
        validate_github_url(payload.github_url)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc

    repo = await RepositoryRepository(db).create(
        project_id=project_id, github_url=payload.github_url, branch=payload.branch
    )
    await db.commit()
    return repo


@router.get("/projects/{project_id}/repositories", response_model=list[RepositoryOut])
async def list_repositories(
    project_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    project = await ProjectRepository(db).get_owned(project_id, current_user.id)
    if project is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")
    return await RepositoryRepository(db).list_for_project(project_id)


@router.get("/repositories/{repository_id}", response_model=RepositoryOut)
async def get_repository(
    repository_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    repo = await RepositoryRepository(db).get_owned(repository_id, current_user.id)
    if repo is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Repository not found")
    return repo


@router.post(
    "/repositories/{repository_id}/index",
    response_model=IndexTriggerResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def trigger_indexing(
    repository_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Publishes a `repository.index.requested` event and returns immediately
    with a job_id. The API never blocks waiting for indexing -- that work
    happens asynchronously in the Kafka worker. Poll GET /repositories/{id}
    or GET /indexing-jobs/{job_id} for status.
    """
    repo_dal = RepositoryRepository(db)
    repo = await repo_dal.get_owned(repository_id, current_user.id)
    if repo is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Repository not found")

    job = await repo_dal.create_job(repository_id)
    await repo_dal.update_status(repository_id, IndexStatus.QUEUED)
    await db.commit()

    publish_event(
        settings.TOPIC_INDEX_REQUESTED,
        key=str(repository_id),
        payload={
            "job_id": str(job.id),
            "repository_id": str(repository_id),
            "project_id": str(repo.project_id),
            "github_url": repo.github_url,
            "branch": repo.branch,
        },
    )

    return IndexTriggerResponse(job_id=job.id, repository_id=repository_id, status=IndexStatus.QUEUED)


@router.get("/indexing-jobs/{job_id}")
async def get_indexing_job(
    job_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    repo_dal = RepositoryRepository(db)
    job = await repo_dal.get_job(job_id)
    if job is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found")
    # Authorization: confirm the job's repository belongs to this user.
    owned_repo = await repo_dal.get_owned(job.repository_id, current_user.id)
    if owned_repo is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found")
    return {
        "job_id": job.id,
        "repository_id": job.repository_id,
        "status": job.status,
        "chunks_indexed": job.chunks_indexed,
        "error_message": job.error_message,
        "duration_ms": job.duration_ms,
    }
