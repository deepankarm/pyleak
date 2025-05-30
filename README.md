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

