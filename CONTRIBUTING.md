# Contributing to vcpkg-harbor

Thank you for your interest in contributing to vcpkg-harbor! This document provides guidelines and instructions for contributing.

## Code of Conduct

Please read and follow our [Code of Conduct](CODE_OF_CONDUCT.md).

## How to Contribute

### Reporting Bugs

If you find a bug, please open an issue on GitHub with:

- A clear, descriptive title
- Steps to reproduce the issue
- Expected behavior vs actual behavior
- Your environment (OS, Python version, storage backend)
- Relevant logs or error messages

### Suggesting Features

Feature suggestions are welcome! Please open an issue with:

- A clear description of the feature
- The problem it solves or use case
- Any implementation ideas you have

### Pull Requests

1. **Fork the repository** and create your branch from `main`
2. **Set up development environment**:
   ```bash
   ./scripts/setup-dev.sh
   ```
3. **Make your changes** following our coding standards
4. **Add tests** for new functionality
5. **Run the test suite**:
   ```bash
   ./scripts/test.sh
   ```
6. **Run the linter**:
   ```bash
   ./scripts/lint.sh
   ```
7. **Commit your changes** with a clear commit message
8. **Push to your fork** and submit a pull request

## Development Setup

### Prerequisites

- Python 3.11+
- Docker and Docker Compose (optional, for testing with MinIO)

### Quick Start

```bash
# Clone your fork
git clone https://github.com/YOUR_USERNAME/vcpkg-harbor.git
cd vcpkg-harbor

# Set up development environment
./scripts/setup-dev.sh

# Start development server
./scripts/dev-server.sh

# Run tests
./scripts/test.sh

# Run linter
./scripts/lint.sh
```

### Project Structure

```
src/vcpkg_harbor/
├── core/           # Configuration, logging, exceptions
├── api/            # REST API endpoints
├── storage/        # Storage backends (filesystem, MinIO, S3, etc.)
├── auth/           # Authentication middleware
├── dashboard/      # Web dashboard (templates, routes)
├── services/       # Business logic services
└── static/         # Static assets
```

## Coding Standards

### Python Style

- Follow [PEP 8](https://peps.python.org/pep-0008/)
- Use type hints for function signatures
- Maximum line length: 100 characters
- Use `ruff` for linting and formatting

### Code Organization

- Keep modules focused and single-purpose
- Use dependency injection where appropriate
- Write docstrings for public functions and classes

### Testing

- Write tests for new functionality
- Maintain test coverage above 80%
- Use pytest fixtures for common setup
- Test both success and error cases

### Commit Messages

- Use clear, descriptive commit messages
- Start with a verb (Add, Fix, Update, Remove, etc.)
- Reference issues when applicable: `Fix #123: Description`

## Adding a Storage Backend

vcpkg-harbor uses a plugin architecture for storage backends. To add a new backend:

1. Create a new module in `src/vcpkg_harbor/storage/backends/`
2. Implement the `StorageBackend` protocol from `storage/base.py`
3. Add configuration classes to `core/config.py`
4. Register the entry point in `pyproject.toml`:
   ```toml
   [project.entry-points."vcpkg_harbor.storage"]
   mybackend = "vcpkg_harbor.storage.backends.mybackend:MyBackend"
   ```
5. Add tests in `tests/storage/`
6. Update documentation

## Documentation

- Update documentation for user-facing changes
- Add docstrings to new public APIs
- Test documentation locally:
  ```bash
  ./scripts/docs.sh serve
  ```

## Questions?

Feel free to open an issue or start a discussion on GitHub if you have questions about contributing.
