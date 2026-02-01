"""
Handlers package for Amul Product Alert Bot.
"""

from handlers.user import (
    start_command,
    add_command,
    proof_command,
    handle_proof_photo,
    subscription_command,
    rules_command,
    dm_command,
    help_command,
    pause_command,
    resume_command,
    preferences_command,
    alert_settings_command,
    quiet_hours_command,
    getalert_command,
)

from handlers.admin import (
    auto_approve_command,
    settings_command,
    reply_command,
    stats_command,
    broadcast_command,
    extend_command,
    block_command,
    unblock_command,
    approve_command,
    admin_help_command,
)

__all__ = [
    # User handlers
    'start_command',
    'add_command',
    'proof_command',
    'handle_proof_photo',
    'subscription_command',
    'rules_command',
    'dm_command',
    'help_command',
    'pause_command',
    'resume_command',
    'preferences_command',
    'alert_settings_command',
    'quiet_hours_command',
    'getalert_command',
    # Admin handlers
    'auto_approve_command',
    'settings_command',
    'reply_command',
    'stats_command',
    'broadcast_command',
    'extend_command',
    'block_command',
    'unblock_command',
    'approve_command',
    'admin_help_command',
]
