"""empty message

Revision ID: 524f3bc13241
Revises: 7919dee3fcf5
Create Date: 2023-08-01 22:24:11.194684

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql

# revision identifiers, used by Alembic.
revision = '524f3bc13241'
down_revision = '7919dee3fcf5'
branch_labels = None
depends_on = None


def upgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    with op.batch_alter_table('user', schema=None) as batch_op:
        batch_op.alter_column('user_id',
               existing_type=mysql.VARCHAR(length=50),
               nullable=False)

    # ### end Alembic commands ###


def downgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    with op.batch_alter_table('user', schema=None) as batch_op:
        batch_op.alter_column('user_id',
               existing_type=mysql.VARCHAR(length=50),
               nullable=True)

    # ### end Alembic commands ###
