"""Add quality_lab_runs and quality_lab_results tables for #714 Quality Lab.

Revision ID: b2c3d4e5f6a7
Create Date: 2026-06-14
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "b2c3d4e5f6a7"
down_revision: str | None = "z0a1b2c3d4e5"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "quality_lab_runs",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "eval_config",
            sa.Text(),
            nullable=False,
            comment="Named configuration (default, reranker, hierarchy-expansion, etc.)",
        ),
        sa.Column(
            "git_commit",
            sa.Text(),
            nullable=True,
            comment="Git commit SHA the eval was run against",
        ),
        sa.Column(
            "summary",
            sa.JSON(),
            nullable=False,
            comment="Aggregate metrics (recall@k, MRR, citation_accuracy, etc.)",
        ),
        sa.Column("case_count", sa.Integer(), nullable=False),
        sa.Column("passed_count", sa.Integer(), nullable=False),
        sa.Column("pass_rate", sa.Float(), nullable=False),
        sa.Column(
            "created_by",
            sa.Text(),
            nullable=True,
            comment="User who uploaded the run",
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )

    op.create_table(
        "quality_lab_results",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "run_id",
            sa.Uuid(),
            sa.ForeignKey("quality_lab_runs.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "case_id",
            sa.Text(),
            nullable=False,
        ),
        sa.Column(
            "category",
            sa.Text(),
            nullable=False,
        ),
        sa.Column(
            "passed",
            sa.Boolean(),
            nullable=False,
        ),
        sa.Column(
            "result_json",
            sa.JSON(),
            nullable=False,
            comment="Full per-case result dict from the eval harness",
        ),
    )

    op.create_index(
        "ix_quality_lab_results_run_id",
        "quality_lab_results",
        ["run_id"],
    )
    op.create_index(
        "ix_quality_lab_runs_created_at",
        "quality_lab_runs",
        ["created_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_quality_lab_runs_created_at", table_name="quality_lab_runs")
    op.drop_index("ix_quality_lab_results_run_id", table_name="quality_lab_results")
    op.drop_table("quality_lab_results")
    op.drop_table("quality_lab_runs")
