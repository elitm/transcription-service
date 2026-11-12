import pytest
from app.infrastructure.job_queue import JobQueue, QueueFullError


@pytest.mark.unit
class TestJobQueueEnqueue:

    def test_enqueue_adds_job_to_queue(self, max_queue_depth):
        queue = JobQueue(max_depth=max_queue_depth)
        job_id = "job-123"

        queue.enqueue(job_id)

        assert queue.size() == 1

    def test_enqueue_multiple_jobs_increases_size(self, max_queue_depth):
        queue = JobQueue(max_depth=max_queue_depth)

        queue.enqueue("job-1")
        queue.enqueue("job-2")
        queue.enqueue("job-3")

        assert queue.size() == 3

    def test_enqueue_raises_when_queue_full(self, max_queue_depth):
        queue = JobQueue(max_depth=max_queue_depth)

        for i in range(max_queue_depth):
            queue.enqueue(f"job-{i}")

        with pytest.raises(QueueFullError):
            queue.enqueue("job-overflow")


@pytest.mark.unit
class TestJobQueueDequeue:

    def test_dequeue_returns_fifo_order(self, max_queue_depth):
        queue = JobQueue(max_depth=max_queue_depth)

        queue.enqueue("job-1")
        queue.enqueue("job-2")
        queue.enqueue("job-3")

        assert queue.dequeue() == "job-1"
        assert queue.dequeue() == "job-2"
        assert queue.dequeue() == "job-3"

    def test_dequeue_reduces_size(self, max_queue_depth):
        queue = JobQueue(max_depth=max_queue_depth)
        queue.enqueue("job-1")
        queue.enqueue("job-2")

        queue.dequeue()

        assert queue.size() == 1

    def test_dequeue_empty_returns_none(self, max_queue_depth):
        queue = JobQueue(max_depth=max_queue_depth)

        result = queue.dequeue()

        assert result is None

    def test_dequeue_after_full_allows_new_enqueue(self, max_queue_depth):
        queue = JobQueue(max_depth=max_queue_depth)

        for i in range(max_queue_depth):
            queue.enqueue(f"job-{i}")

        queue.dequeue()

        queue.enqueue("job-new")
        assert queue.size() == max_queue_depth


@pytest.mark.unit
class TestJobQueueStatus:

    def test_is_full_when_at_max_depth(self, max_queue_depth):
        queue = JobQueue(max_depth=max_queue_depth)

        for i in range(max_queue_depth):
            queue.enqueue(f"job-{i}")

        assert queue.is_full() is True

    def test_is_full_false_when_not_full(self, max_queue_depth):
        queue = JobQueue(max_depth=max_queue_depth)
        queue.enqueue("job-1")

        assert queue.is_full() is False

    def test_is_full_false_when_empty(self, max_queue_depth):
        queue = JobQueue(max_depth=max_queue_depth)

        assert queue.is_full() is False

    def test_size_empty_queue(self, max_queue_depth):
        queue = JobQueue(max_depth=max_queue_depth)

        assert queue.size() == 0
