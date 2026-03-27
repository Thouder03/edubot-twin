import pytest
from datetime import datetime, timedelta
from app.crud import container_metrics as metrics_crud
from app.schemas.container_metrics import ContainerMetricsCreate

@pytest.mark.asyncio
async def test_create_metrics(db_session):
    metrics_in = ContainerMetricsCreate(
        container_id=1,
        cpu_percent=50.5,
        memory_mb=512,
        collection_status="success"
    )
    metrics = await metrics_crud.create_metrics(db_session, metrics_in)
    assert metrics.cpu_percent == 50.5
    assert metrics.memory_mb == 512

@pytest.mark.asyncio
async def test_cleanup_old_metrics(db_session):
    old_time = datetime.utcnow() - timedelta(days=8)
    metrics_in = ContainerMetricsCreate(
        container_id=1,
        cpu_percent=50.0,
        memory_mb=512,
        collection_status="success"
    )
    await metrics_crud.create_metrics(db_session, metrics_in)
    deleted = await metrics_crud.cleanup_old_metrics(db_session, days=7)
    assert deleted >= 0
