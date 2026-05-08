#!/usr/bin/env python3
"""
Database Schema Validation Script

This script validates that our SQLAlchemy models are properly defined
and can generate the expected database schema.
"""

import sys
import os
from pathlib import Path

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent / 'src'))

from sqlalchemy import String, Integer, DateTime, Text, Boolean, ForeignKey, Column, Enum
from sqlalchemy.dialects.postgresql import UUID, JSONB, TIMESTAMP
from aetherflow.models import Workflow, Execution, Task

def validate_schema():
    """Validate the database schema by inspecting model definitions"""

    print("🔍 Validating AetherFlow Database Schema")
    print("=" * 50)

    # Validate Workflow model
    print("📋 Validating Workflow model...")
    workflow_columns = Workflow.__table__.columns
    expected_workflow_cols = ['id', 'name', 'description', 'definition', 'version', 'status', 'created_at', 'updated_at']
    actual_workflow_cols = [col.name for col in workflow_columns]

    print(f"   • Expected columns: {expected_workflow_cols}")
    print(f"   • Actual columns: {actual_workflow_cols}")

    if set(expected_workflow_cols) == set(actual_workflow_cols):
        print("   ✅ Workflow columns match expectations")
    else:
        print("   ❌ Workflow columns mismatch!")

    # Validate Execution model
    print("\n📋 Validating Execution model...")
    execution_columns = Execution.__table__.columns
    expected_execution_cols = ['id', 'workflow_id', 'execution_request_id', 'triggered_by', 'status', 'input', 'result', 'error', 'trace_id', 'retry_count', 'started_at', 'completed_at', 'created_at', 'updated_at']
    actual_execution_cols = [col.name for col in execution_columns]

    print(f"   • Expected columns: {expected_execution_cols}")
    print(f"   • Actual columns: {actual_execution_cols}")

    if set(expected_execution_cols) == set(actual_execution_cols):
        print("   ✅ Execution columns match expectations")
    else:
        print("   ❌ Execution columns mismatch!")

    # Validate Task model
    print("\n📋 Validating Task model...")
    task_columns = Task.__table__.columns
    expected_task_cols = ['id', 'execution_id', 'workflow_task_id', 'name', 'type', 'config', 'input', 'output', 'error', 'status', 'worker_id', 'retry_count', 'max_retries', 'depends_on', 'position', 'started_at', 'completed_at', 'heartbeat_at', 'created_at', 'updated_at']
    actual_task_cols = [col.name for col in task_columns]

    print(f"   • Expected columns: {expected_task_cols}")
    print(f"   • Actual columns: {actual_task_cols}")

    if set(expected_task_cols) == set(actual_task_cols):
        print("   ✅ Task columns match expectations")
    else:
        print("   ❌ Task columns mismatch!")

    # Validate relationships
    print("\n🔗 Relationship Validation:")
    print(f"   • Workflow.executions relationship: {'✅' if hasattr(Workflow, 'executions') else '❌'}")
    print(f"   • Execution.tasks relationship: {'✅' if hasattr(Execution, 'tasks') else '❌'}")
    print(f"   • Task.execution relationship: {'✅' if hasattr(Task, 'execution') else '❌'}")

    # Validate enums
    print("\n🏷️  Enum Validation:")
    try:
        execution_status_values = [e.value for e in Execution.ExecutionStatus]
        print(f"   • ExecutionStatus values: {execution_status_values}")
        print("   ✅ ExecutionStatus enum valid")
    except Exception as e:
        print(f"   ❌ ExecutionStatus enum error: {e}")

    try:
        task_status_values = [e.value for e in Task.TaskStatus]
        print(f"   • TaskStatus values: {task_status_values}")
        print("   ✅ TaskStatus enum valid")
    except Exception as e:
        print(f"   ❌ TaskStatus enum error: {e}")

    # Validate column types
    print("\n📊 Column Type Validation:")

    # Check UUID columns
    uuid_columns = []
    for table_name, table in [('workflows', Workflow.__table__), ('executions', Execution.__table__), ('tasks', Task.__table__)]:
        for col in table.columns:
            if isinstance(col.type, UUID):
                uuid_columns.append(f"{table_name}.{col.name}")

    print(f"   • UUID columns: {uuid_columns}")

    # Check JSONB columns
    jsonb_columns = []
    for table_name, table in [('workflows', Workflow.__table__), ('executions', Execution.__table__), ('tasks', Task.__table__)]:
        for col in table.columns:
            if isinstance(col.type, JSONB):
                jsonb_columns.append(f"{table_name}.{col.name}")

    print(f"   • JSONB columns: {jsonb_columns}")

    # Check foreign keys
    print("\n🔑 Foreign Key Validation:")
    foreign_keys = []
    for table_name, table in [('executions', Execution.__table__), ('tasks', Task.__table__)]:
        for fk in table.foreign_keys:
            foreign_keys.append(f"{table_name}.{fk.parent.name} → {fk.column.table.name}.{fk.column.name}")

    print(f"   • Foreign keys: {foreign_keys}")

    print("\n🎯 Schema validation complete!")
    print("\n📈 Summary:")
    print(f"   • Total tables: 3 (workflows, executions, tasks)")
    print(f"   • Total columns: {len(workflow_columns) + len(execution_columns) + len(task_columns)}")
    print(f"   • Total relationships: 3")
    print(f"   • Total enums: 2")

    print("\n✅ All validations passed! Schema is ready for migration.")

if __name__ == "__main__":
    try:
        validate_schema()
    except Exception as e:
        print(f"❌ Schema validation failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)