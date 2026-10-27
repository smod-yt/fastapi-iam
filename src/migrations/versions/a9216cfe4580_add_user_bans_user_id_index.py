from typing import Sequence, Union

from alembic import op

revision: str = "a9216cfe4580"
down_revision: Union[str, Sequence[str], None] = "31ddc7a4129b"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_index("ix_user_bans_user_id", "user_bans", ["user_id"])


def downgrade() -> None:
    op.drop_index("ix_user_bans_user_id", table_name="user_bans")
