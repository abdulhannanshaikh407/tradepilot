"""add kill switch, signal state machine, system config

Revision ID: a1b2c3d4e5f6
Revises: 5fd272de1f65
Create Date: 2026-09-07 00:00:00.000000+00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'a1b2c3d4e5f6'
down_revision: Union[str, None] = '5fd272de1f65'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Users: add kill_switch column for per-user trading halt
    op.add_column('users', sa.Column('kill_switch', sa.Boolean(), nullable=False, server_default='0'))
    op.create_index(op.f('ix_users_kill_switch'), 'users', ['kill_switch'], unique=False)

    # Signals: add signal state machine columns
    op.add_column('signals', sa.Column('signal_state', sa.String(), nullable=False, server_default='WATCHING'))
    op.add_column('signals', sa.Column('invalidation_reason', sa.Text(), nullable=True))
    op.add_column('signals', sa.Column('quality_score', sa.Float(), nullable=True))
    op.create_index(op.f('ix_signals_user_state'), 'signals', ['user_id', 'signal_state'], unique=False)

    # System config table for app-wide kill switch and global settings
    op.create_table('system_config',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('key', sa.String(), nullable=False),
        sa.Column('value', sa.JSON(), nullable=True),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_system_config_key'), 'system_config', ['key'], unique=True)


def downgrade() -> None:
    op.drop_index(op.f('ix_system_config_key'), table_name='system_config')
    op.drop_table('system_config')
    op.drop_index(op.f('ix_signals_user_state'), table_name='signals')
    op.drop_column('signals', 'quality_score')
    op.drop_column('signals', 'invalidation_reason')
    op.drop_column('signals', 'signal_state')
    op.drop_index(op.f('ix_users_kill_switch'), table_name='users')
    op.drop_column('users', 'kill_switch')
