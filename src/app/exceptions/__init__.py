
# app/
# │
# ├── exceptions/
# │   ├── __init__.py                
# │   ├── base.py                    # App-level errors (e.g. RepositoryError, DuplicateError)
# │   ├── integrity_classifier.py    # SQL-level / DB-specific errors
# │   ├── mapper.py                  # Map SQL-level / DB-specific errors to app-level errors
# │   └── validators.py              # Repository-level validation utilities
