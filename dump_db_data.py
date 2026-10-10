"""
从当前数据库导出初始化数据为 SQL 语句
用于替换 schema.sql 中的 5 个内置账户
"""
import pymysql
from datetime import datetime, date

conn = pymysql.connect(host='127.0.0.1', port=3306, user='root', password='2023011630', database='ie_project_db', charset='utf8mb4')
cur = conn.cursor(pymysql.cursors.DictCursor)

PASSWORD_HASH = '$2b$12$BkvT/g5j4FB6WBPDYjWIHe53NopXAA4jq.fL02krwlW51bP3z1C9W'  # 对应明文 123456

def esc(val):
    """转义 SQL 值"""
    if val is None:
        return 'NULL'
    if isinstance(val, bool):
        return '1' if val else '0'
    if isinstance(val, (int, float)):
        return str(val)
    if isinstance(val, (datetime, date)):
        return f"'{val.strftime('%Y-%m-%d %H:%M:%S')}'"
    if isinstance(val, bytes):
        val = val.decode('utf-8', errors='replace')
    s = str(val).replace("\\", "\\\\").replace("'", "\\'")
    return f"'{s}'"

def dump_table(table, columns, where=None, order_by=None):
    """导出表数据为 INSERT 语句"""
    sql = f"SELECT {', '.join(columns)} FROM `{table}`"
    if where:
        sql += f" WHERE {where}"
    if order_by:
        sql += f" ORDER BY {order_by}"
    cur.execute(sql)
    rows = cur.fetchall()
    if not rows:
        return f"-- {table}: 无数据\n", 0
    lines = []
    lines.append(f"-- {table}: {len(rows)} rows")
    lines.append(f"INSERT INTO `{table}` ({', '.join(columns)}) VALUES")
    value_lines = []
    for row in rows:
        vals = [esc(row[col]) for col in columns]
        value_lines.append(f"  ({', '.join(vals)})")
    lines.append(',\n'.join(value_lines) + ';')
    return '\n'.join(lines) + '\n', len(rows)

# 按外键依赖顺序导出
output = []
output.append("-- ====================================================================")
output.append("-- 初始化数据（基于实际业务数据生成）")
output.append("-- 所有用户密码统一为 123456（bcrypt 加密）")
output.append("-- ====================================================================")
output.append("")

# 1. sys_college
sql, n = dump_table('sys_college', ['id', 'college_code', 'college_name', 'dean_id', 'sort_order', 'status'], order_by='id')
output.append(sql)

# 2. sys_user
user_cols = ['id', 'username', 'password_hash', 'real_name', 'email', 'phone', 'role', 'college_id', 'avatar', 'status', 'force_change_pwd', 'last_login_at', 'last_login_ip', 'is_deleted']
sql, n = dump_table('sys_user', user_cols, order_by='id')
output.append(sql)

# 3. sys_dict
sql, n = dump_table('sys_dict', ['id', 'dict_type', 'dict_code', 'dict_label', 'dict_value', 'sort_order', 'status', 'remark'], order_by='id')
output.append(sql)

# 4. biz_competition
cur.execute("SELECT COLUMN_NAME FROM information_schema.COLUMNS WHERE TABLE_SCHEMA='ie_project_db' AND TABLE_NAME='biz_competition' ORDER BY ORDINAL_POSITION")
comp_cols = [r['COLUMN_NAME'] for r in cur.fetchall()]
sql, n = dump_table('biz_competition', comp_cols, order_by='id')
output.append(sql)

# 5. biz_announcement
cur.execute("SELECT COLUMN_NAME FROM information_schema.COLUMNS WHERE TABLE_SCHEMA='ie_project_db' AND TABLE_NAME='biz_announcement' ORDER BY ORDINAL_POSITION")
ann_cols = [r['COLUMN_NAME'] for r in cur.fetchall()]
sql, n = dump_table('biz_announcement', ann_cols, order_by='id')
output.append(sql)

# 6. sys_attachment
cur.execute("SELECT COLUMN_NAME FROM information_schema.COLUMNS WHERE TABLE_SCHEMA='ie_project_db' AND TABLE_NAME='sys_attachment' ORDER BY ORDINAL_POSITION")
att_cols = [r['COLUMN_NAME'] for r in cur.fetchall()]
sql, n = dump_table('sys_attachment', att_cols, order_by='id')
output.append(sql)

# 7. proj_project
cur.execute("SELECT COLUMN_NAME FROM information_schema.COLUMNS WHERE TABLE_SCHEMA='ie_project_db' AND TABLE_NAME='proj_project' ORDER BY ORDINAL_POSITION")
proj_cols = [r['COLUMN_NAME'] for r in cur.fetchall()]
sql, n = dump_table('proj_project', proj_cols, order_by='id')
output.append(sql)

# 8. proj_team_member
cur.execute("SELECT COLUMN_NAME FROM information_schema.COLUMNS WHERE TABLE_SCHEMA='ie_project_db' AND TABLE_NAME='proj_team_member' ORDER BY ORDINAL_POSITION")
tm_cols = [r['COLUMN_NAME'] for r in cur.fetchall()]
sql, n = dump_table('proj_team_member', tm_cols, order_by='id')
output.append(sql)

# 9. proj_budget
cur.execute("SELECT COLUMN_NAME FROM information_schema.COLUMNS WHERE TABLE_SCHEMA='ie_project_db' AND TABLE_NAME='proj_budget' ORDER BY ORDINAL_POSITION")
bud_cols = [r['COLUMN_NAME'] for r in cur.fetchall()]
sql, n = dump_table('proj_budget', bud_cols, order_by='id')
output.append(sql)

# 10. proj_review
cur.execute("SELECT COLUMN_NAME FROM information_schema.COLUMNS WHERE TABLE_SCHEMA='ie_project_db' AND TABLE_NAME='proj_review' ORDER BY ORDINAL_POSITION")
rev_cols = [r['COLUMN_NAME'] for r in cur.fetchall()]
sql, n = dump_table('proj_review', rev_cols, order_by='id')
output.append(sql)

# 11. proj_expense
cur.execute("SELECT COLUMN_NAME FROM information_schema.COLUMNS WHERE TABLE_SCHEMA='ie_project_db' AND TABLE_NAME='proj_expense' ORDER BY ORDINAL_POSITION")
exp_cols = [r['COLUMN_NAME'] for r in cur.fetchall()]
sql, n = dump_table('proj_expense', exp_cols, order_by='id')
output.append(sql)

# 12. proj_achievement
cur.execute("SELECT COLUMN_NAME FROM information_schema.COLUMNS WHERE TABLE_SCHEMA='ie_project_db' AND TABLE_NAME='proj_achievement' ORDER BY ORDINAL_POSITION")
ach_cols = [r['COLUMN_NAME'] for r in cur.fetchall()]
sql, n = dump_table('proj_achievement', ach_cols, order_by='id')
output.append(sql)

# 13. proj_midterm_check
cur.execute("SELECT COLUMN_NAME FROM information_schema.COLUMNS WHERE TABLE_SCHEMA='ie_project_db' AND TABLE_NAME='proj_midterm_check' ORDER BY ORDINAL_POSITION")
mt_cols = [r['COLUMN_NAME'] for r in cur.fetchall()]
sql, n = dump_table('proj_midterm_check', mt_cols, order_by='id')
output.append(sql)

# 14. proj_change_request
cur.execute("SELECT COLUMN_NAME FROM information_schema.COLUMNS WHERE TABLE_SCHEMA='ie_project_db' AND TABLE_NAME='proj_change_request' ORDER BY ORDINAL_POSITION")
cr_cols = [r['COLUMN_NAME'] for r in cur.fetchall()]
sql, n = dump_table('proj_change_request', cr_cols, order_by='id')
output.append(sql)

result = '\n'.join(output)
with open('d:/SoftwareEngineering/ieproject/init_data.sql', 'w', encoding='utf-8') as f:
    f.write(result)

print(f"导出完成，共 {len(result)} 字符")
print(f"文件已保存到: d:/SoftwareEngineering/ieproject/init_data.sql")

# 统计
cur.execute("SELECT COUNT(*) AS cnt FROM sys_user")
print(f"sys_user: {cur.fetchone()['cnt']} users")

cur.close()
conn.close()
