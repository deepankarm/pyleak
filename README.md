# pyleak

Detect leaked asyncio tasks in Python. Inspired by Go's [goleak](https://github.com/uber-go/goleak).

## Installation

```bash
pip install pyleak
```

## Usage

### Context Manager

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

### Decorator

```python
@no_task_leaks()
async def test_my_function():
    await my_async_function()
    # Any leaked tasks will be detected when the function exits
```

### Actions

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

### Name Filtering

Only detect tasks matching specific names:

```python
import re

# Exact match
async with no_task_leaks(name_filter="background-worker"):
    pass

# Regex pattern
async with no_task_leaks(name_filter=re.compile(r"worker-\d+")):
    pass
```

## Testing

Perfect for catching leaked tasks in tests:

```python
import pytest
from pyleak import no_task_leaks

@no_task_leaks(action="raise")
async def test_no_leaked_tasks():
    # Test will fail if any tasks are leaked
    await my_function_under_test()

class TestMyApp:
    async def test_with_context_manager(self):
        async with no_task_leaks(action="raise"):
            await my_async_operation()
```

More examples can be found in the [tests](./tests/test_task_leaks.py).
