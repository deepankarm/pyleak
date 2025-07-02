# pyleak

<a href="https://pypi.org/project/pyleak/"><img alt="PyPI" src="https://img.shields.io/pypi/v/pyleak?label=Release&style=flat-square"></a>
<a href="https://pepy.tech/projects/pyleak"><img src="https://static.pepy.tech/badge/pyleak/month" alt="PyPI Downloads"></a>

Detect leaked asyncio tasks, threads, and event loop blocking in Python. Inspired by Go's [goleak](https://github.com/uber-go/goleak).

## Installation

```bash
pip install pyleak
```

## Quick Start

```python
import asyncio
from pyleak import no_task_leaks, no_thread_leaks, no_event_loop_blocking

# Detect leaked asyncio tasks
async def main():
    async with no_task_leaks():
        asyncio.create_task(asyncio.sleep(10))  # This will be detected
        await asyncio.sleep(0.1)

# Detect leaked threads  
def sync_main():
    with no_thread_leaks():
        threading.Thread(target=lambda: time.sleep(10)).start()  # This will be detected

# Detect event loop blocking
async def async_main():
    with no_event_loop_blocking():
        time.sleep(0.5)  # This will be detected
```

## Usage

### Context Managers

All detectors can be used as context managers:

```python
# AsyncIO tasks (async context)
async with no_task_leaks():
    # Your async code here
    pass

# Threads (sync context)
with no_thread_leaks():
    # Your threaded code here
    pass

# Event loop blocking (async context only)
async def main():
    with no_event_loop_blocking():
        # Your potentially blocking code here
        pass
```

### Decorators  

All detectors can also be used as decorators:

```python
@no_task_leaks()
async def my_async_function():
    # Any leaked tasks will be detected
    pass

@no_thread_leaks()
def my_threaded_function():
    # Any leaked threads will be detected  
    pass

@no_event_loop_blocking()
async def my_potentially_blocking_function():
    # Any event loop blocking will be detected
    pass
```

### Get stack trace 

#### From leaked asyncio tasks

When using `no_task_leaks`, you get detailed stack trace information showing exactly where leaked tasks are executing and where they were created.


```python
import asyncio
from pyleak import TaskLeakError, no_task_leaks

async def leaky_function():
    async def background_task():
        print("background task started")
        await asyncio.sleep(10)

    print("creating a long running task")
    asyncio.create_task(background_task())

async def main():
    try:
        async with no_task_leaks(action="raise"):
            await leaky_function()
    except TaskLeakError as e:
        print(e)

if __name__ == "__main__":
    asyncio.run(main())
```

Output:

```
creating a long running task
background task started
Detected 1 leaked asyncio tasks

Leaked Task: Task-2
  ID: 4345977088
  State: TaskState.RUNNING
  Current Stack:
    File "/tmp/example.py", line 9, in background_task
        await asyncio.sleep(10)
```


#### Include creation stack trace

You can also include the creation stack trace by passing `enable_creation_tracking=True` to `no_task_leaks`.

```python
async def main():
    try:
        async with no_task_leaks(action="raise", enable_creation_tracking=True):
            await leaky_function()
    except TaskLeakError as e:
        print(e)
```

Output:

```
creating a long running task
background task started
Detected 1 leaked asyncio tasks

Leaked Task: Task-2
  ID: 4392245504
  State: TaskState.RUNNING
  Current Stack:
    File "/tmp/example.py", line 9, in background_task
        await asyncio.sleep(10)
  Creation Stack:
    File "/tmp/example.py", line 24, in <module>
        asyncio.run(main())
    File "/opt/homebrew/.../asyncio/runners.py", line 194, in run
        return runner.run(main)
    File "/opt/homebrew/.../asyncio/runners.py", line 118, in run
        return self._loop.run_until_complete(task)
    File "/opt/homebrew/.../asyncio/base_events.py", line 671, in run_until_complete
        self.run_forever()
    File "/opt/homebrew/.../asyncio/base_events.py", line 638, in run_forever
        self._run_once()
    File "/opt/homebrew/.../asyncio/base_events.py", line 1971, in _run_once
        handle._run()
    File "/opt/homebrew/.../asyncio/events.py", line 84, in _run
        self._context.run(self._callback, *self._args)
    File "/tmp/example.py", line 18, in main
        await leaky_function()
    File "/tmp/example.py", line 12, in leaky_function
        asyncio.create_task(background_task())
```

`TaskLeakError` has a `leaked_tasks` attribute that contains a list of `LeakedTask` objects including the stack trace details.

> Note: `enable_creation_tracking` monkey patches `asyncio.create_task` to include the creation stack trace. It is not recommended to be used in production to avoid unnecessary side effects.

#### From event loop blocks

When using `no_event_loop_blocking`, you get detailed stack trace information showing exactly where the event loop is blocked and where the blocking code is executing.

```python
import asyncio
import time

from pyleak import EventLoopBlockError, no_event_loop_blocking


async def some_function_with_blocking_code():
    print("starting")
    time.sleep(1)
    print("done")


async def main():
    try:
        async with no_event_loop_blocking(action="raise"):
            await some_function_with_blocking_code()
    except EventLoopBlockError as e:
        print(e)


if __name__ == "__main__":
    asyncio.run(main())
```

Output:

```
starting
done
Detected 1 event loop blocks

Event Loop Block: block-1
  Duration: 0.605s (threshold: 0.200s)
  Timestamp: 1749051796.302
  Blocking Stack:
    File "/private/tmp/example.py", line 22, in <module>
        asyncio.run(main())
      File "/opt/homebrew/.../asyncio/runners.py", line 194, in run
        return runner.run(main)
      File "/opt/homebrew/.../asyncio/runners.py", line 118, in run
        return self._loop.run_until_complete(task)
      File "/opt/homebrew/.../asyncio/base_events.py", line 671, in run_until_complete
        self.run_forever()
      File "/opt/homebrew/.../asyncio/base_events.py", line 638, in run_forever
        self._run_once()
      File "/opt/homebrew/.../asyncio/base_events.py", line 1971, in _run_once
        handle._run()
      File "/opt/homebrew/.../asyncio/events.py", line 84, in _run
        self._context.run(self._callback, *self._args)
      File "/private/tmp/example.py", line 16, in main
        await some_function_with_blocking_code()
      File "/private/tmp/example.py", line 9, in some_function_with_blocking_code
        time.sleep(1)
```

## Actions

Control what happens when leaks/blocking are detected:

| Action | AsyncIO Tasks | Threads | Event Loop Blocking |
|--------|---------------|---------|-------------------|
| `"warn"` (default) | ✅ Issues `ResourceWarning` | ✅ Issues `ResourceWarning` | ✅ Issues ResourceWarning |
| `"log"` | ✅ Writes to logger | ✅ Writes to logger | ✅ Writes to logger |
| `"cancel"` | ✅ Cancels leaked tasks | ❌ Warns (can't force-stop) | ❌ Warns (can't cancel) |
| `"raise"` | ✅ Raises `TaskLeakError` | ✅ Raises `ThreadLeakError` | ✅ Raises `EventLoopBlockError` |

```python
# Examples
async with no_task_leaks(action="cancel"):  # Cancels leaked tasks
    pass

with no_thread_leaks(action="raise"):  # Raises exception on thread leaks
    pass

with no_event_loop_blocking(action="log"):  # Logs blocking events
    pass
```

## Name Filtering

Filter detection by resource names (tasks and threads only):

```python
import re

# Exact match
async with no_task_leaks(name_filter="background-worker"):
    pass

with no_thread_leaks(name_filter="worker-thread"):
    pass

# Regex pattern
async with no_task_leaks(name_filter=re.compile(r"worker-\d+")):
    pass

with no_thread_leaks(name_filter=re.compile(r"background-.*")):
    pass
```

> Note: Event loop blocking detection doesn't support name filtering.

## Configuration Options

### AsyncIO Tasks
```python
no_task_leaks(
    action="warn",           # Action to take on detection
    name_filter=None,        # Filter by task name
    logger=None              # Custom logger
)
```

### Threads  
```python
no_thread_leaks(
    action="warn",           # Action to take on detection
    name_filter=None,        # Filter by thread name
    logger=None,             # Custom logger
    exclude_daemon=True,     # Exclude daemon threads
)
```

### Event Loop Blocking
```python
no_event_loop_blocking(
    action="warn",           # Action to take on detection
    logger=None,             # Custom logger
    threshold=0.1,           # Minimum blocking time to report (seconds)
    check_interval=0.01      # How often to check (seconds)
)
```

## Testing

Perfect for catching issues in tests:

```python
import pytest
from pyleak import no_task_leaks, no_thread_leaks, no_event_loop_blocking

@pytest.mark.asyncio
async def test_no_leaked_tasks():
    async with no_task_leaks(action="raise"):
        await my_async_function()

def test_no_leaked_threads():
    with no_thread_leaks(action="raise"):
        my_threaded_function()

@pytest.mark.asyncio        
async def test_no_event_loop_blocking():
    with no_event_loop_blocking(action="raise", threshold=0.1):
        await my_potentially_blocking_function()
```

## Real-World Examples

### Detecting Synchronous HTTP Calls in Async Code

```python
import httpx
from starlette.testclient import TestClient

async def test_sync_vs_async_http():
    # This will detect blocking
    with no_event_loop_blocking(action="warn"):
        response = TestClient(app).get("/endpoint")  # Synchronous!
        
    # This will not detect blocking  
    with no_event_loop_blocking(action="warn"):
        async with httpx.AsyncClient() as client:
            response = await client.get("/endpoint")  # Asynchronous!
```

### Ensuring Proper Resource Cleanup

```python
async def test_background_task_cleanup():
    async with no_task_leaks(action="raise"):
        # This would fail the test
        asyncio.create_task(long_running_task())
        
        # This would pass
        task = asyncio.create_task(long_running_task())
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
```

### Debugging complex task leaks

```python
import asyncio
import random
import re
from pyleak import TaskLeakError, no_task_leaks

async def debug_task_leaks():
    """Example showing how to debug complex task leaks."""

    async def worker(worker_id: int, sleep_time: int):
        print(f"Worker {worker_id} starting")
        await asyncio.sleep(sleep_time)  # Simulate work
        print(f"Worker {worker_id} done")

    async def spawn_workers():
        for i in range(3):
            asyncio.create_task(worker(i, random.randint(1, 10)), name=f"worker-{i}")

    try:
        async with no_task_leaks(
            action="raise",
            enable_creation_tracking=True,
            name_filter=re.compile(r"worker-\d+"),  # Only catch worker tasks
        ):
            await spawn_workers()
            await asyncio.sleep(0.1)  # Let workers start

    except TaskLeakError as e:
        print(f"\nFound {e.task_count} leaked worker tasks:")
        for task_info in e.leaked_tasks:
            print(f"\n--- {task_info.name} ---")
            print("Currently executing:")
            print(task_info.format_current_stack())
            print("Created at:")
            print(task_info.format_creation_stack())

            # Cancel the leaked task
            if task_info.task_ref:
                task_info.task_ref.cancel()


if __name__ == "__main__":
    asyncio.run(debug_task_leaks())

```


<details>
<summary><b>Toggle to see the output</b></summary>

```
Worker 0 starting
Worker 1 starting
Worker 2 starting

Found 3 leaked worker tasks:

--- worker-2 ---
Currently executing:
  File "/private/tmp/example.py", line 33, in worker
    await asyncio.sleep(sleep_time)  # Simulate work

Created at:
  File "/private/tmp/example.py", line 65, in <module>
    asyncio.run(debug_task_leaks())
  File "/opt/homebrew/anaconda3/envs/ffa/lib/python3.12/asyncio/runners.py", line 194, in run
    return runner.run(main)
  File "/opt/homebrew/anaconda3/envs/ffa/lib/python3.12/asyncio/runners.py", line 118, in run
    return self._loop.run_until_complete(task)
  File "/opt/homebrew/anaconda3/envs/ffa/lib/python3.12/asyncio/base_events.py", line 671, in run_until_complete
    self.run_forever()
  File "/opt/homebrew/anaconda3/envs/ffa/lib/python3.12/asyncio/base_events.py", line 638, in run_forever
    self._run_once()
  File "/opt/homebrew/anaconda3/envs/ffa/lib/python3.12/asyncio/base_events.py", line 1971, in _run_once
    handle._run()
  File "/opt/homebrew/anaconda3/envs/ffa/lib/python3.12/asyncio/events.py", line 84, in _run
    self._context.run(self._callback, *self._args)
  File "/private/tmp/example.py", line 47, in debug_task_leaks
    await spawn_workers()
  File "/private/tmp/example.py", line 39, in spawn_workers
    asyncio.create_task(worker(i, random.randint(1, 10)), name=f"worker-{i}")


--- worker-0 ---
Currently executing:
  File "/private/tmp/example.py", line 33, in worker
    await asyncio.sleep(sleep_time)  # Simulate work

Created at:
  File "/private/tmp/example.py", line 65, in <module>
    asyncio.run(debug_task_leaks())
  File "/opt/homebrew/anaconda3/envs/ffa/lib/python3.12/asyncio/runners.py", line 194, in run
    return runner.run(main)
  File "/opt/homebrew/anaconda3/envs/ffa/lib/python3.12/asyncio/runners.py", line 118, in run
    return self._loop.run_until_complete(task)
  File "/opt/homebrew/anaconda3/envs/ffa/lib/python3.12/asyncio/base_events.py", line 671, in run_until_complete
    self.run_forever()
  File "/opt/homebrew/anaconda3/envs/ffa/lib/python3.12/asyncio/base_events.py", line 638, in run_forever
    self._run_once()
  File "/opt/homebrew/anaconda3/envs/ffa/lib/python3.12/asyncio/base_events.py", line 1971, in _run_once
    handle._run()
  File "/opt/homebrew/anaconda3/envs/ffa/lib/python3.12/asyncio/events.py", line 84, in _run
    self._context.run(self._callback, *self._args)
  File "/private/tmp/example.py", line 47, in debug_task_leaks
    await spawn_workers()
  File "/private/tmp/example.py", line 39, in spawn_workers
    asyncio.create_task(worker(i, random.randint(1, 10)), name=f"worker-{i}")


--- worker-1 ---
Currently executing:
  File "/private/tmp/example.py", line 33, in worker
    await asyncio.sleep(sleep_time)  # Simulate work

Created at:
  File "/private/tmp/example.py", line 65, in <module>
    asyncio.run(debug_task_leaks())
  File "/opt/homebrew/anaconda3/envs/ffa/lib/python3.12/asyncio/runners.py", line 194, in run
    return runner.run(main)
  File "/opt/homebrew/anaconda3/envs/ffa/lib/python3.12/asyncio/runners.py", line 118, in run
    return self._loop.run_until_complete(task)
  File "/opt/homebrew/anaconda3/envs/ffa/lib/python3.12/asyncio/base_events.py", line 671, in run_until_complete
    self.run_forever()
  File "/opt/homebrew/anaconda3/envs/ffa/lib/python3.12/asyncio/base_events.py", line 638, in run_forever
    self._run_once()
  File "/opt/homebrew/anaconda3/envs/ffa/lib/python3.12/asyncio/base_events.py", line 1971, in _run_once
    handle._run()
  File "/opt/homebrew/anaconda3/envs/ffa/lib/python3.12/asyncio/events.py", line 84, in _run
    self._context.run(self._callback, *self._args)
  File "/private/tmp/example.py", line 47, in debug_task_leaks
    await spawn_workers()
  File "/private/tmp/example.py", line 39, in spawn_workers
    asyncio.create_task(worker(i, random.randint(1, 10)), name=f"worker-{i}")
```

</details>

### Debugging event loop blocking

```python
import asyncio
from pyleak import EventLoopBlockError, no_event_loop_blocking

async def process_user_data(user_id: int):
    """Simulates cpu intensive work - contains blocking operations!"""
    print(f"Processing user {user_id}...")
    return sum(i * i for i in range(100_000_000))

async def main():
    try:
        async with no_event_loop_blocking(action="raise", threshold=0.5):
            user1 = await process_user_data(1)
            user2 = await process_user_data(2)

    except EventLoopBlockError as e:
        print(f"\n🚨 Found {e.block_count} blocking events:")
        print(e)

if __name__ == "__main__":
    asyncio.run(main())
```


<details>
<summary><b>Toggle to see the output</b></summary>

```
Processing user 1...
Processing user 2...

🚨 Found 5 blocking events:
Detected 5 event loop blocks

Event Loop Block: block-1
  Duration: 1.507s (threshold: 0.500s)
  Timestamp: 1749052720.456
  Blocking Stack:
    File "/private/tmp/example.py", line 36, in <module>
        asyncio.run(main())
      File "/opt/homebrew/anaconda3/envs/ffa/lib/python3.12/asyncio/runners.py", line 194, in run
        return runner.run(main)
      File "/opt/homebrew/anaconda3/envs/ffa/lib/python3.12/asyncio/runners.py", line 118, in run
        return self._loop.run_until_complete(task)
      File "/opt/homebrew/anaconda3/envs/ffa/lib/python3.12/asyncio/base_events.py", line 671, in run_until_complete
        self.run_forever()
      File "/opt/homebrew/anaconda3/envs/ffa/lib/python3.12/asyncio/base_events.py", line 638, in run_forever
        self._run_once()
      File "/opt/homebrew/anaconda3/envs/ffa/lib/python3.12/asyncio/base_events.py", line 1971, in _run_once
        handle._run()
      File "/opt/homebrew/anaconda3/envs/ffa/lib/python3.12/asyncio/events.py", line 84, in _run
        self._context.run(self._callback, *self._args)
      File "/private/tmp/example.py", line 27, in main
        user1 = await process_user_data(1)
      File "/private/tmp/example.py", line 21, in process_user_data
        return sum(i * i for i in range(100_000_000))
      File "/private/tmp/example.py", line 21, in <genexpr>
        return sum(i * i for i in range(100_000_000))
Event Loop Block: block-2
  Duration: 1.516s (threshold: 0.500s)
  Timestamp: 1749052722.054
  Blocking Stack:
    File "/private/tmp/example.py", line 36, in <module>
        asyncio.run(main())
      File "/opt/homebrew/anaconda3/envs/ffa/lib/python3.12/asyncio/runners.py", line 194, in run
        return runner.run(main)
      File "/opt/homebrew/anaconda3/envs/ffa/lib/python3.12/asyncio/runners.py", line 118, in run
        return self._loop.run_until_complete(task)
      File "/opt/homebrew/anaconda3/envs/ffa/lib/python3.12/asyncio/base_events.py", line 671, in run_until_complete
        self.run_forever()
      File "/opt/homebrew/anaconda3/envs/ffa/lib/python3.12/asyncio/base_events.py", line 638, in run_forever
        self._run_once()
      File "/opt/homebrew/anaconda3/envs/ffa/lib/python3.12/asyncio/base_events.py", line 1971, in _run_once
        handle._run()
      File "/opt/homebrew/anaconda3/envs/ffa/lib/python3.12/asyncio/events.py", line 84, in _run
        self._context.run(self._callback, *self._args)
      File "/private/tmp/example.py", line 27, in main
        user1 = await process_user_data(1)
      File "/private/tmp/example.py", line 21, in process_user_data
        return sum(i * i for i in range(100_000_000))
      File "/private/tmp/example.py", line 21, in <genexpr>
        return sum(i * i for i in range(100_000_000))
Event Loop Block: block-3
  Duration: 1.518s (threshold: 0.500s)
  Timestamp: 1749052723.648
  Blocking Stack:
    File "/private/tmp/example.py", line 36, in <module>
        asyncio.run(main())
      File "/opt/homebrew/anaconda3/envs/ffa/lib/python3.12/asyncio/runners.py", line 194, in run
        return runner.run(main)
      File "/opt/homebrew/anaconda3/envs/ffa/lib/python3.12/asyncio/runners.py", line 118, in run
        return self._loop.run_until_complete(task)
      File "/opt/homebrew/anaconda3/envs/ffa/lib/python3.12/asyncio/base_events.py", line 671, in run_until_complete
        self.run_forever()
      File "/opt/homebrew/anaconda3/envs/ffa/lib/python3.12/asyncio/base_events.py", line 638, in run_forever
        self._run_once()
      File "/opt/homebrew/anaconda3/envs/ffa/lib/python3.12/asyncio/base_events.py", line 1971, in _run_once
        handle._run()
      File "/opt/homebrew/anaconda3/envs/ffa/lib/python3.12/asyncio/events.py", line 84, in _run
        self._context.run(self._callback, *self._args)
      File "/private/tmp/example.py", line 28, in main
        user2 = await process_user_data(2)
      File "/private/tmp/example.py", line 21, in process_user_data
        return sum(i * i for i in range(100_000_000))
      File "/private/tmp/example.py", line 21, in <genexpr>
        return sum(i * i for i in range(100_000_000))
Event Loop Block: block-4
  Duration: 1.517s (threshold: 0.500s)
  Timestamp: 1749052725.247
  Blocking Stack:
    File "/private/tmp/example.py", line 36, in <module>
        asyncio.run(main())
      File "/opt/homebrew/anaconda3/envs/ffa/lib/python3.12/asyncio/runners.py", line 194, in run
        return runner.run(main)
      File "/opt/homebrew/anaconda3/envs/ffa/lib/python3.12/asyncio/runners.py", line 118, in run
        return self._loop.run_until_complete(task)
      File "/opt/homebrew/anaconda3/envs/ffa/lib/python3.12/asyncio/base_events.py", line 671, in run_until_complete
        self.run_forever()
      File "/opt/homebrew/anaconda3/envs/ffa/lib/python3.12/asyncio/base_events.py", line 638, in run_forever
        self._run_once()
      File "/opt/homebrew/anaconda3/envs/ffa/lib/python3.12/asyncio/base_events.py", line 1971, in _run_once
        handle._run()
      File "/opt/homebrew/anaconda3/envs/ffa/lib/python3.12/asyncio/events.py", line 84, in _run
        self._context.run(self._callback, *self._args)
      File "/private/tmp/example.py", line 28, in main
        user2 = await process_user_data(2)
      File "/private/tmp/example.py", line 21, in process_user_data
        return sum(i * i for i in range(100_000_000))
      File "/private/tmp/example.py", line 21, in <genexpr>
        return sum(i * i for i in range(100_000_000))
Event Loop Block: block-5
  Duration: 1.513s (threshold: 0.500s)
  Timestamp: 1749052726.839
  Blocking Stack:
    File "/private/tmp/example.py", line 36, in <module>
        asyncio.run(main())
      File "/opt/homebrew/anaconda3/envs/ffa/lib/python3.12/asyncio/runners.py", line 194, in run
        return runner.run(main)
      File "/opt/homebrew/anaconda3/envs/ffa/lib/python3.12/asyncio/runners.py", line 118, in run
        return self._loop.run_until_complete(task)
      File "/opt/homebrew/anaconda3/envs/ffa/lib/python3.12/asyncio/base_events.py", line 671, in run_until_complete
        self.run_forever()
      File "/opt/homebrew/anaconda3/envs/ffa/lib/python3.12/asyncio/base_events.py", line 638, in run_forever
        self._run_once()
      File "/opt/homebrew/anaconda3/envs/ffa/lib/python3.12/asyncio/base_events.py", line 1971, in _run_once
        handle._run()
      File "/opt/homebrew/anaconda3/envs/ffa/lib/python3.12/asyncio/events.py", line 84, in _run
        self._context.run(self._callback, *self._args)
      File "/private/tmp/example.py", line 28, in main
        user2 = await process_user_data(2)
      File "/private/tmp/example.py", line 21, in process_user_data
        return sum(i * i for i in range(100_000_000))
      File "/private/tmp/example.py", line 21, in <genexpr>
        return sum(i * i for i in range(100_000_000))
```
</details>


## Pytest Plugin

The pytest plugin automatically wraps tests with pyleak detectors based on pytest markers.

### Installation

```bash
pip install pyleak
```

### Add the plugin to your pytest configuration

**pyproject.toml**

```toml
[tool.pytest.ini_options]
markers = [
    "no_leaks: detect asyncio task leaks, thread leaks, and event loop blocking"
]
```

**pytest.ini**

```ini
[tool:pytest]
markers = no_leaks: detect asyncio task leaks, thread leaks, and event loop blocking
```

You can also add it to the `conftest.py` file.

```python
# conftest.py
import pytest

def pytest_configure(config):
    config.addinivalue_line(
        "markers", 
        "no_leaks: detect asyncio task leaks, thread leaks, and event loop blocking"
    )
```

### Usage

```python
@pytest.mark.no_leaks
@pytest.mark.asyncio
async def test_no_task_leaks():
    asyncio.create_task(asyncio.sleep(10))
```

### Selective detection

By default, all detectors are enabled. You can selectively enable or disable detectors using the `no_leaks` marker. For example, to only detect task leaks and event loop blocking, you can use the following:

```python
@pytest.mark.no_leaks(tasks=True, blocking=True, threads=False)
@pytest.mark.asyncio
async def test_async_no_leaks():
    asyncio.create_task(asyncio.sleep(10))  # This will be detected
    time.sleep(0.5)  # This will be detected
    threading.Thread(target=lambda: time.sleep(10)).start()  # This will not be detected
```

#### `no_leaks` marker configuration

| Name | Default | Description |
|:------|:------|:------|
| tasks | True | Whether to detect task leaks |
| task_action | raise | Action to take when a task leak is detected |
| task_name_filter | None | Filter to apply to task names |
| enable_task_creation_tracking | False | Whether to enable task creation tracking |
| threads | True | Whether to detect thread leaks |
| thread_action | raise | Action to take when a thread leak is detected |
| thread_name_filter | r'^(?!asyncio_\\d+$).*' | Filter to apply to thread names (default: exclude asyncio threads) |
| exclude_daemon_threads | True | Whether to exclude daemon threads |
| blocking | True | Whether to detect event loop blocking |
| blocking_action | raise | Action to take when a blocking event loop is detected |
| blocking_threshold | 0.2 | Threshold for blocking event loop detection |
| blocking_check_interval | 0.01 | Interval for checking for blocking event loop |


## Why Use pyleak?

**AsyncIO Tasks**: Leaked tasks can cause memory leaks, prevent graceful shutdown, and make debugging difficult.

**Threads**: Leaked threads consume system resources and can prevent proper application termination.

**Event Loop Blocking**: Synchronous operations in async code destroy performance and can cause timeouts.

`pyleak` helps you catch these issues during development and testing, optionally using a pytest plugin, before they reach production.

## Examples

More examples can be found in the test files:
- [AsyncIO tasks tests](./tests/test_task_leaks.py) 
- [Thread tests](./tests/test_thread_leaks.py)
- [Event loop blocking tests](./tests/test_event_loop_blocking.py)
- [Pytest plugin tests](./tests/test_plugin.py)

---

> Disclaimer: Most of the code and tests are written by Claude.
