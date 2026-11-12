import pytest
import asyncio
from app.services.event_broadcaster import EventBroadcaster


@pytest.fixture
def broadcaster():
    return EventBroadcaster()


@pytest.mark.unit
class TestEventBroadcasterSubscribe:

    async def test_subscribe_returns_async_iterator(self, broadcaster):
        job_id = "job-1"

        iterator = broadcaster.subscribe(job_id)

        assert hasattr(iterator, "__aiter__")

    async def test_publish_sends_to_subscriber(self, broadcaster):
        job_id = "job-2"
        event = {"status": "processing"}

        async def collect_events():
            events = []
            async for evt in broadcaster.subscribe(job_id):
                events.append(evt)
                if len(events) >= 1:
                    break
            return events

        task = asyncio.create_task(collect_events())
        await asyncio.sleep(0.01)

        await broadcaster.publish(job_id, event)

        result = await task

        assert len(result) >= 1
        assert result[0] == event


@pytest.mark.unit
class TestEventBroadcasterSingleSubscriber:

    async def test_only_one_subscriber_allowed(self, broadcaster):
        job_id = "job-3"

        async def subscribe():
            async for _ in broadcaster.subscribe(job_id):
                pass

        task1 = asyncio.create_task(subscribe())
        await asyncio.sleep(0.01)

        with pytest.raises(ValueError, match="already has an active subscriber"):
            async for _ in broadcaster.subscribe(job_id):
                pass

        task1.cancel()
        try:
            await task1
        except asyncio.CancelledError:
            pass


@pytest.mark.unit
class TestEventBroadcasterIsolation:

    async def test_events_isolated_by_job_id(self, broadcaster):
        job_1_event = {"status": "processing", "job_id": "job-1"}
        job_2_event = {"status": "completed", "job_id": "job-2"}

        async def collect_events(job_id):
            events = []
            async for evt in broadcaster.subscribe(job_id):
                events.append(evt)
                if len(events) >= 1:
                    break
            return events

        task1 = asyncio.create_task(collect_events("job-1"))
        task2 = asyncio.create_task(collect_events("job-2"))
        await asyncio.sleep(0.01)

        await broadcaster.publish("job-1", job_1_event)
        await broadcaster.publish("job-2", job_2_event)

        result1 = await task1
        result2 = await task2

        assert result1[0]["job_id"] == "job-1"
        assert result2[0]["job_id"] == "job-2"


