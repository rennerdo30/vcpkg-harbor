# Contributing

Thank you for your interest in contributing to vcpkg-harbor!

## Development Setup

1. **Clone the repository**

   ```bash
   git clone https://github.com/rennerdo30/vcpkg-harbor.git
   cd vcpkg-harbor
   ```

2. **Run the setup script**

   ```bash
   ./scripts/setup-dev.sh
   ```

   This creates a virtual environment and installs all dependencies.

3. **Activate the environment**

   ```bash
   source .venv/bin/activate
   ```

4. **Start the development server**

   ```bash
   ./scripts/dev-server.sh
   ```

## Code Style

We use `ruff` for linting and formatting:

```bash
# Run linter
ruff check src/

# Run formatter
ruff format src/

# Or use the script
./scripts/lint.sh
```

## Type Checking

We use `mypy` for type checking:

```bash
mypy src/vcpkg_harbor --ignore-missing-imports
```

## Testing

Run the test suite:

```bash
# Run all tests
./scripts/test.sh

# Run specific tests
pytest tests/test_health.py -v

# Run with coverage
pytest tests/ --cov=vcpkg_harbor --cov-report=html
```

## Pull Request Process

1. **Fork the repository** and create a feature branch
2. **Make your changes** with appropriate tests
3. **Run the linter and tests** before committing
4. **Write clear commit messages**
5. **Open a pull request** with a description of your changes

## Commit Messages

Follow conventional commits:

```
feat: add Azure Blob storage backend
fix: handle connection timeout in MinIO backend
docs: update configuration documentation
test: add tests for authentication middleware
```

## Adding a Storage Backend

To add a new storage backend:

1. Create `src/vcpkg_harbor/storage/backends/mybackend.py`
2. Implement the `StorageBackend` protocol
3. Add entry point in `pyproject.toml`
4. Add configuration settings
5. Write tests
6. Update documentation

See [Architecture](architecture.md) for details on the protocol.

## Questions?

Open an issue on GitHub or start a discussion.
