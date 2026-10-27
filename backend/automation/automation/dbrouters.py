# yourproject/dbrouters.py

class MSSQLRouter:
    """
    Route models that opt in via `use_mssql = True` to the MSSQL database.
    - Reads for MSSQL models go to 'mssql'
    - Writes to MSSQL models are blocked (read-only)
    - Migrations never run on 'mssql'
    """

    def db_for_read(self, model, **hints):
        if getattr(model, "use_mssql", False):
            return "mssql"
        return None  # default routing

    def db_for_write(self, model, **hints):
        if getattr(model, "use_mssql", False):
            # Route writes to MSSQL *if attempted*, but we will block them below in ReadOnlyModel.
            # Returning "mssql" keeps it explicit which DB it would target.
            return "mssql"
        return None

    def allow_relation(self, obj1, obj2, **hints):
        # Allow relations only within the same DB type
        m1 = getattr(obj1.__class__, "use_mssql", False)
        m2 = getattr(obj2.__class__, "use_mssql", False)
        if m1 == m2:
            return True
        return False

    def allow_migrate(self, db, app_label, model_name=None, **hints):
        # Absolutely *no* migrations on MSSQL
        if db == "mssql":
            return False
        # Allow migrations on SQLite
        return True
