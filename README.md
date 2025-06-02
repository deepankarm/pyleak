# pyleak

Detect leaked asyncio tasks and threads in Python. Inspired by Go's [goleak](https://github.com/uber-go/goleak).

## Installation

```bash
pip install pyleak
```

## Usage

### Asyncio Tasks

#### Context Manager

```python
# script.py
import asyncio
from pyleak import no_task_leaks

async def main():
    async with no_task_leaks():
        # This will detect any tasks that aren't properly awaited
        asyncio.create_task(asyncio.sleep(10), name="my-task")  # This would be flagged
        await asyncio.sleep(0.1)

asyncio.run(main())
```

```bash
python -W always script.py
# ResourceWarning: Detected 1 leaked asyncio tasks: ['my-task']
```

#### Decorator

```python
@no_task_leaks()
async def test_my_function():
    await my_async_function()
    # Any leaked tasks will be detected when the function exits
```

#### Actions

Choose what happens when leaks are detected:

```python
# Warn (default) - issues a ResourceWarning
async with no_task_leaks(action="warn"):
    pass

# Log - writes to logger
async with no_task_leaks(action="log"):
    pass

# Cancel - cancels the leaked tasks
async with no_task_leaks(action="cancel"):
    pass

# Raise - raises TaskLeakError
async with no_task_leaks(action="raise"):
    pass
```

### Threads

#### Context Manager

```python
import threading
from pyleak import no_thread_leaks

def main():
    with no_thread_leaks():
        # This will detect any threads that aren't properly joined
        threading.Thread(target=lambda: time.sleep(10)).start()

main()
```

```bash
python -W always script.py
# ResourceWarning: Detected 1 leaked threads: ['Thread-1']
```

#### Decorator

```python
from pyleak import no_thread_leaks

@no_thread_leaks()
def main():
    threading.Thread(target=lambda: time.sleep(10)).start()

main()
```

#### Actions

Note: Cancelling threads is not supported. It will only warn about them.

```python
from pyleak import no_thread_leaks

# Warn (default) - issues a ResourceWarning
with no_thread_leaks(action="warn"):
    pass

# Log - writes to logger
with no_thread_leaks(action="log"):
    pass


# Raise - raises ThreadLeakError
with no_thread_leaks(action="raise"):
    pass
```

### Name Filtering

Only detect tasks matching specific names:

```python
import re
from pyleak import no_task_leaks

# Exact match
async with no_task_leaks(name_filter="background-worker"):
    pass

# Regex pattern
async with no_task_leaks(name_filter=re.compile(r"worker-\d+")):
    pass
```

## Testing

Perfect for catching leaked tasks and threads in tests:

```python
import pytest
from pyleak import no_task_leaks, no_thread_leaks

@pytest.mark.asyncio
async def test_no_leaked_tasks():
    async with no_task_leaks(action="raise"):
        await my_async_function()


def test_no_leaked_threads():
    with no_thread_leaks(action="raise"):
        threading.Thread(target=my_function).start()

```

More examples can be found in the [asyncio tasks tests](./tests/test_task_leaks.py) and [thread tests](./tests/test_thread_leaks.py).


> Disclaimer: Most of the code is written by Claude. 


# pyleak

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

## Why Use pyleak?

**AsyncIO Tasks**: Leaked tasks can cause memory leaks, prevent graceful shutdown, and make debugging difficult.

**Threads**: Leaked threads consume system resources and can prevent proper application termination.

**Event Loop Blocking**: Synchronous operations in async code destroy performance and can cause timeouts.

`pyleak` helps you catch these issues during development and testing, before they reach production.

## Examples

More examples can be found in the test files:
- [AsyncIO tasks tests](./tests/test_task_leaks.py) 
- [Thread tests](./tests/test_thread_leaks.py)
- [Event loop blocking tests](./tests/test_event_loop_blocking.py)

---

> Disclaimer: Most of the code and tests are written by Claude.
