"""临时脚本：重置用户密码哈希"""
import pymysql
from passlib.context import CryptContext

# 创建密码哈希上下文
ctx = CryptContext(schemes=["bcrypt"], deprecated="auto")

# 生成新的密码哈希
new_hash = ctx.hash("admin123")
print(f"New hash: {new_hash}")

# 连接数据库
conn = pymysql.connect(
    host="host.docker.internal",
    port=3306,
    user="root",
    password="2023011630",
    database="ie_project_db"
)

cursor = conn.cursor()
cursor.execute("UPDATE sys_user SET password_hash=%s", (new_hash,))
conn.commit()
print(f"Updated {cursor.rowcount} rows")

# 验证
cursor.execute("SELECT username, password_hash FROM sys_user LIMIT 5")
for row in cursor.fetchall():
    print(f"  User: {row[0]}, Hash: {row[1][:20]}...")

cursor.close()
conn.close()
print("Done!")
