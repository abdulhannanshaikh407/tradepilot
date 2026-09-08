"""add missing tables: autotrade_configs, positions, alert_preferences,
device_tokens, broker_connections, real_positions, real_trades

Revision ID: b2c3d4e5f6g7
Revises: a1b2c3d4e5f6
Create Date: 2026-09-09 00:00:00.000000+00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'b2c3d4e5f6g7'
down_revision: Union[str, None] = 'a1b2c3d4e5f6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # broker_connections
    op.create_table('broker_connections',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('broker_name', sa.String(), nullable=False),
        sa.Column('api_key_encrypted', sa.Text(), nullable=False),
        sa.Column('api_secret_encrypted', sa.Text(), nullable=False),
        sa.Column('account_type', sa.String(), nullable=False, server_default='paper'),
        sa.Column('account_id', sa.String(), nullable=True),
        sa.Column('is_verified', sa.Boolean(), nullable=True, server_default='false'),
        sa.Column('last_verified_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('last_error', sa.String(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=True, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(['user_id'], ['users.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_broker_connections_id'), 'broker_connections', ['id'], unique=False)

    # autotrade_configs
    op.create_table('autotrade_configs',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('strategy_id', sa.Integer(), nullable=False),
        sa.Column('broker_connection_id', sa.Integer(), nullable=True),
        sa.Column('enabled', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('mode', sa.String(), nullable=False, server_default='paper'),
        sa.Column('capital', sa.Float(), nullable=False, server_default='10000.0'),
        sa.Column('risk_percent', sa.Float(), nullable=False, server_default='1.0'),
        sa.Column('slippage_percent', sa.Float(), nullable=False, server_default='0.1'),
        sa.Column('max_concurrent', sa.Integer(), nullable=False, server_default='1'),
        sa.Column('max_daily_loss', sa.Float(), nullable=True),
        sa.Column('cooldown_minutes', sa.Integer(), nullable=False, server_default='60'),
        sa.Column('last_run_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('last_error', sa.String(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=True, server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['user_id'], ['users.id']),
        sa.ForeignKeyConstraint(['strategy_id'], ['strategies.id']),
        sa.ForeignKeyConstraint(['broker_connection_id'], ['broker_connections.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_autotradeconfigs_enabled'), 'autotrade_configs', ['enabled'], unique=False)

    # positions
    op.create_table('positions',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('strategy_id', sa.Integer(), nullable=True),
        sa.Column('signal_id', sa.Integer(), nullable=True),
        sa.Column('symbol', sa.String(), nullable=False),
        sa.Column('direction', sa.String(), nullable=False),
        sa.Column('handler', sa.String(), nullable=False, server_default='autotrade'),
        sa.Column('broker', sa.String(), nullable=False, server_default='paper'),
        sa.Column('status', sa.String(), nullable=False, server_default='OPEN'),
        sa.Column('entry_price', sa.Float(), nullable=True),
        sa.Column('current_price', sa.Float(), nullable=True),
        sa.Column('stop_loss', sa.Float(), nullable=True),
        sa.Column('take_profit', sa.Float(), nullable=True),
        sa.Column('size', sa.Float(), nullable=True),
        sa.Column('cost', sa.Float(), nullable=True),
        sa.Column('unrealized_pnl', sa.Float(), nullable=True),
        sa.Column('realized_pnl', sa.Float(), nullable=True),
        sa.Column('pnl_percent', sa.Float(), nullable=True),
        sa.Column('exit_reason', sa.String(), nullable=True),
        sa.Column('opened_at', sa.DateTime(timezone=True), nullable=True, server_default=sa.func.now()),
        sa.Column('closed_at', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['user_id'], ['users.id']),
        sa.ForeignKeyConstraint(['strategy_id'], ['strategies.id']),
        sa.ForeignKeyConstraint(['signal_id'], ['signals.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_positions_id'), 'positions', ['id'], unique=False)
    op.create_index('ix_positions_user_status', 'positions', ['user_id', 'status'], unique=False)

    # alert_preferences
    op.create_table('alert_preferences',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('strategy_id', sa.Integer(), nullable=False),
        sa.Column('alerts_enabled', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('push_enabled', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('email_enabled', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('in_app_enabled', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('min_confidence', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=True, server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['user_id'], ['users.id']),
        sa.ForeignKeyConstraint(['strategy_id'], ['strategies.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_alert_preferences_id'), 'alert_preferences', ['id'], unique=False)

    # device_tokens
    op.create_table('device_tokens',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('token', sa.String(), nullable=False),
        sa.Column('platform', sa.String(), nullable=False, server_default='android'),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=True, server_default=sa.func.now()),
        sa.Column('last_used_at', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['user_id'], ['users.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_device_tokens_id'), 'device_tokens', ['id'], unique=False)
    op.create_index(op.f('ix_device_tokens_token'), 'device_tokens', ['token'], unique=True)

    # real_positions
    op.create_table('real_positions',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('broker_connection_id', sa.Integer(), nullable=False),
        sa.Column('symbol', sa.String(), nullable=False),
        sa.Column('quantity', sa.Float(), nullable=False),
        sa.Column('entry_price', sa.Float(), nullable=False),
        sa.Column('current_price', sa.Float(), nullable=False),
        sa.Column('pnl', sa.Float(), nullable=True, server_default='0'),
        sa.Column('pnl_percent', sa.Float(), nullable=True, server_default='0'),
        sa.Column('opened_at', sa.DateTime(timezone=True), nullable=True, server_default=sa.func.now()),
        sa.Column('synced_at', sa.DateTime(timezone=True), nullable=True, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(['user_id'], ['users.id']),
        sa.ForeignKeyConstraint(['broker_connection_id'], ['broker_connections.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_real_positions_id'), 'real_positions', ['id'], unique=False)

    # real_trades
    op.create_table('real_trades',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('broker_connection_id', sa.Integer(), nullable=False),
        sa.Column('strategy_id', sa.Integer(), nullable=True),
        sa.Column('symbol', sa.String(), nullable=False),
        sa.Column('side', sa.String(), nullable=False),
        sa.Column('quantity', sa.Float(), nullable=False),
        sa.Column('entry_price', sa.Float(), nullable=False),
        sa.Column('exit_price', sa.Float(), nullable=True),
        sa.Column('pnl', sa.Float(), nullable=True),
        sa.Column('pnl_percent', sa.Float(), nullable=True),
        sa.Column('opened_at', sa.DateTime(timezone=True), nullable=True, server_default=sa.func.now()),
        sa.Column('closed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('status', sa.String(), nullable=False, server_default='open'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id']),
        sa.ForeignKeyConstraint(['broker_connection_id'], ['broker_connections.id']),
        sa.ForeignKeyConstraint(['strategy_id'], ['strategies.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_real_trades_id'), 'real_trades', ['id'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_real_trades_id'), table_name='real_trades')
    op.drop_table('real_trades')
    op.drop_index(op.f('ix_real_positions_id'), table_name='real_positions')
    op.drop_table('real_positions')
    op.drop_index(op.f('ix_device_tokens_token'), table_name='device_tokens')
    op.drop_index(op.f('ix_device_tokens_id'), table_name='device_tokens')
    op.drop_table('device_tokens')
    op.drop_index(op.f('ix_alert_preferences_id'), table_name='alert_preferences')
    op.drop_table('alert_preferences')
    op.drop_index('ix_positions_user_status', table_name='positions')
    op.drop_index(op.f('ix_positions_id'), table_name='positions')
    op.drop_table('positions')
    op.drop_index(op.f('ix_autotradeconfigs_enabled'), table_name='autotrade_configs')
    op.drop_table('autotrade_configs')
    op.drop_index(op.f('ix_broker_connections_id'), table_name='broker_connections')
    op.drop_table('broker_connections')
